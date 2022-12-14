import math
import numpy as np
import time
import os
import config

import torch
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.parameter import Parameter
from torch.nn.modules.module import Module
from torch_sparse import spmm   # product between dense matrix and sparse matrix
import torch_sparse as torchsp
from torch_scatter import scatter_add, scatter_max
import torch.sparse as sparse


def layer(layer_type, **kwargs):
    if layer_type == 'GCNConv':
        return GraphConvolution(in_features=kwargs['in_channels'], out_features=kwargs['out_channels'])
    elif layer_type == 'GATConv':
        return MultiHeadAttentionLayer(in_features=kwargs['in_channels'], out_features=kwargs['out_channels'],
                                       heads=kwargs['heads'], dropout=kwargs['dropout'], concat=kwargs['concat'])


class GraphConvolution(torch.nn.Module):
    """
    Simple GCN layer, similar to https://arxiv.org/abs/1609.02907
    """

    def __init__(self, in_features, out_features, bias=True):
        super(GraphConvolution, self).__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.weight = nn.Parameter(torch.FloatTensor(in_features, out_features))
        if bias:
            self.bias = nn.Parameter(torch.FloatTensor(out_features))
        else:
            self.register_parameter('bias', None)
        self.reset_parameters()

    def reset_parameters(self):
        stdv = 1. / math.sqrt(self.weight.size(1))
        self.weight.data.uniform_(-stdv, stdv)
        if self.bias is not None:
            self.bias.data.uniform_(-stdv, stdv)

    def forward(self, input, adj):
        support = torch.mm(input, self.weight)
        output = torch.spmm(adj, support)
        if self.bias is not None:
            return output + self.bias
        else:
            return output

    def __repr__(self):
        return self.__class__.__name__ + ' (' \
               + str(self.in_features) + ' -> ' \
               + str(self.out_features) + ')'


class GraphAttentionLayer(nn.Module):
    """
    Simple GAT layer, similar to https://arxiv.org/abs/1710.10903
    """

    def __init__(self, in_features, out_features, dropout=0., alpha=0.2, concat=True):
        super(GraphAttentionLayer, self).__init__()
        self.dropout = dropout
        self.in_features = in_features
        self.out_features = out_features
        self.alpha = alpha
        self.concat = concat

        self.W = nn.Parameter(torch.empty(size=(in_features, out_features)))
        nn.init.xavier_uniform_(self.W.data, gain=1.414)
        self.a = nn.Parameter(torch.empty(size=(2 * out_features, 1)))
        nn.init.xavier_uniform_(self.a.data, gain=1.414)

        self.leakyrelu = nn.LeakyReLU(self.alpha)

    def forward(self, h, adj):
        Wh = torch.mm(h, self.W)  # h.shape: (N, in_features), Wh.shape: (N, out_features)
        e = self._prepare_attentional_mechanism_input(Wh)

        zero_vec = -9e15 * torch.ones_like(e)
        attention = torch.where(adj > 0, e, zero_vec)
        attention = F.softmax(attention, dim=1)
        attention = F.dropout(attention, self.dropout, training=self.training)
        h_prime = torch.matmul(attention, Wh)

        if self.concat:
            return F.elu(h_prime)
        else:
            return h_prime

    def _prepare_attentional_mechanism_input(self, Wh):
        # Wh.shape (N, out_feature)
        # self.a.shape (2 * out_feature, 1)
        # Wh1&2.shape (N, 1)
        # e.shape (N, N)
        Wh1 = torch.matmul(Wh, self.a[:self.out_features, :])
        Wh2 = torch.matmul(Wh, self.a[self.out_features:, :])
        # broadcast add
        e = Wh1 + Wh2.T
        return self.leakyrelu(e)

    def __repr__(self):
        return self.__class__.__name__ + ' (' + str(self.in_features) + ' -> ' + str(self.out_features) + ')'





class SpecialSpmmFunction(torch.autograd.Function):
    """Special function for only sparse region backpropataion layer."""

    @staticmethod
    def forward(ctx, indices, values, shape, b):
        assert indices.requires_grad == False
        a = torch.sparse_coo_tensor(indices, values, shape)
        ctx.save_for_backward(a, b)
        ctx.N = shape[0]
        return torch.matmul(a, b)

    @staticmethod
    def backward(ctx, grad_output):
        a, b = ctx.saved_tensors
        grad_values = grad_b = None
        if ctx.needs_input_grad[1]:
            grad_a_dense = grad_output.matmul(b.t())
            edge_idx = a._indices()[0, :] * ctx.N + a._indices()[1, :]
            grad_values = grad_a_dense.view(-1)[edge_idx]
        if ctx.needs_input_grad[3]:
            grad_b = a.t().matmul(grad_output)
        return None, grad_values, None, grad_b


class SpecialSpmm(nn.Module):
    def forward(self, indices, values, shape, b):
        return SpecialSpmmFunction.apply(indices, values, shape, b)


class SpGraphAttentionLayer(nn.Module):
    """
    Sparse version GAT layer, similar to https://arxiv.org/abs/1710.10903
    """

    def __init__(self, input_dim, out_dim, dropout=0., alpha=0.2, concat=True):
        super(SpGraphAttentionLayer, self).__init__()
        self.in_features = input_dim
        self.out_features = out_dim
        self.alpha = alpha
        self.concat = concat
        self.dropout = dropout
        self.W = nn.Parameter(torch.zeros(size=(input_dim, out_dim)))  # FxF'
        self.attn = nn.Parameter(torch.zeros(size=(1, 2 * out_dim)))  # 2F'
        nn.init.xavier_normal_(self.W, gain=1.414)
        nn.init.xavier_normal_(self.attn, gain=1.414)
        self.leakyrelu = nn.LeakyReLU(self.alpha)

    def forward(self, x, adj):
        '''
        :param x:   dense tensor. size: nodes*feature_dim
        :param adj:    parse tensor. size: nodes*nodes
        :return:  hidden features
        '''
        N = x.size()[0]  # ???????????????
        edge = adj._indices()  # ??????????????????????????????indices,values??????????????????0????????????????????????edge???????????????edge?????????[2*NoneZero]????????????NoneZero???????????????????????????
        if x.is_sparse:  # ?????????????????????????????????
            h = torch.sparse.mm(x, self.W)
        else:
            h = torch.mm(x, self.W)
        # Self-attention (because including self edges) on the nodes - Shared attention mechanism
        edge_h = torch.cat((h[edge[0, :], :], h[edge[1, :], :]), dim=1).t()  # edge_h: 2*D x E
        values = self.attn.mm(edge_h).squeeze()  # ??????????????????????????????????????????
        edge_e_a = self.leakyrelu(values)  # edge_e_a: E   attetion score for each edge??????????????????????????????leakyrelu??????
        # ??????torch_sparse ?????????softmax??????????????????????????????????????????exp(each-max),????????????
        edge_e = torch.exp(edge_e_a - torch.max(edge_e_a))
        # ??????????????????????????????????????????????????????row sum?????????N*N?????????N*1????????????????????????N*1?????????????????????????????????????????????
        e_rowsum = spmm(edge, edge_e, m=N, n=N,
                        matrix=torch.ones(size=(N, 1)))  # e_rowsum: N x 1???spmm????????????????????????????????????????????????
        h_prime = spmm(edge, edge_e, n=N, m=N, matrix=h)  # ??????????????????????????????????????????????????????
        h_prime = h_prime.div(
            e_rowsum + torch.Tensor([9e-15]))  # h_prime: N x out???div???????????????????????????????????????????????????9e-15???????????????0
        # softmax??????
        if self.concat:
            # if this layer is not last layer
            return F.elu(h_prime)
        else:
            # if this layer is last layer
            return h_prime

    def __repr__(self):
        return self.__class__.__name__ + ' (' + str(self.in_features) + ' -> ' + str(self.out_features) + ')'

class MultiHeadAttentionLayer(nn.Module):
    def __init__(self, in_features, out_features, dropout, heads, concat=True):
        super(MultiHeadAttentionLayer, self).__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.dropout = dropout
        self.attentions = [SpGraphAttentionLayer(in_features, out_features, concat=concat) for _ in range(heads)]
        for i, attention in enumerate(self.attentions):
            self.add_module('attention_{}'.format(i), attention)

    def forward(self, x, adj):
        x = torch.cat([torch.unsqueeze(att(x, adj), 0) for att in self.attentions])
        x = torch.mean(x, dim=0)
        return x

    def __repr__(self):
        return self.__class__.__name__ + ' (' + str(self.in_features) + ' -> ' + str(self.out_features) + ')'