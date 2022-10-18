import torch
import torch.nn as nn
import torch.nn.functional as F
from gae.layer import layer


class GATModelVAE(nn.Module):
    def __init__(self, input_feat_dim, hidden_dim1, hidden_dim2, dropout=0., layerType='GATConv', heads=5 ):
        super(GATModelVAE, self).__init__()
        self.gc1 = layer(layerType, dropout=dropout, in_channels=input_feat_dim, out_channels=hidden_dim1, heads=heads, act=F.relu, concat=False)
        self.gc2 = layer(layerType, dropout=dropout, in_channels=hidden_dim1, out_channels=hidden_dim2, heads=heads, act=lambda x:x, concat=False)
        self.gc3 = layer(layerType, dropout=dropout, in_channels=hidden_dim1, out_channels=hidden_dim2, heads=heads,  act=lambda x:x, concat=False)
        self.dc = InnerProductDecoder(dropout,  act=lambda x:x)

    def encode(self, x, adj):
        hidden1 = self.gc1(x, adj)
        return self.gc2(hidden1, adj), self.gc3(hidden1, adj)

    def reparameterize(self, mu, logvar):
        if self.training:
            std = torch.exp(logvar)
            eps = torch.randn_like(std)
            return eps.mul(std).add_(mu)
        else:
            return mu

    def forward(self, x, adj):
        mu, logvar = self.encode(x, adj)
        z = self.reparameterize(mu, logvar)
        return z, mu, logvar


class InnerProductDecoder(nn.Module):
    """Decoder for using inner product for prediction."""

    def __init__(self, dropout, act=torch.sigmoid):
        super(InnerProductDecoder, self).__init__()
        self.dropout = dropout
        self.act = act


    def forward(self, z):
        z = F.dropout(z, self.dropout, training=self.training)
        adj = self.act(torch.mm(z, z.t()))
        return adj

    # def forward(self, x, edge_index):
    #     z = self.encode(x, edge_index)
    #     x = self.decode(z)
    #    # x = x * size_factors
    #     return x
    #
    # def forward(self, x, edge_index):
    #     mu, logvar = self.encode(x, edge_index)
    #     z = self.reparameterize(mu, logvar)
    #     return z, mu, logvar
