# scGAEGAT

Installation:

(Recommended) Use python virutal environment with conda

conda create -n scgaegatEnv python=3.6.8 pip

conda activate scgaegatEnv

pip install -r requirements.txt


If want to use LTMG (Recommended but Optional, will takes extra time in data preprocessing):

conda install r-devtools

conda install -c cyz931123 r-scgnnltmg

Scripts to reproduce results obtained in the manuscript

Preprocess benchmarks

Option 1 (Recommended): directly use preproceed data

cd Data

tar zxvf benchmarkData.tar.gz 


There are four datasets: Chung, Kolodziejczyk, Klein, Zeisel

Option 2: regenerate preproceed data

1. generating usage csv

Take Dataset Chung for example.

python Preprocessing_benchmark.py --inputfile /Users/wangjue/workspace/scGAEGAT/Data/benchmarkData/Chung/T2000_expression.txt --outputfile /Users/wangjue/workspace/scGAEGAT/Chung.csv --split space --cellheadflag False --cellcount 317

python Preprocessing_benchmark.py --inputfile /Users/wangjue/workspace/scGAEGAT/Data/benchmarkData/Kolodziejczyk/T2000_expression.txt --outputfile /Users/wangjue/workspace/scGAEGAT/Kolodziejczyk.csv --split space --cellheadflag False --cellcount 704

python Preprocessing_benchmark.py --inputfile /Users/wangjue/workspace/scGAEGAT/Data/benchmarkData/Klein/T2000_expression.txt --outputfile /Users/wangjue/workspace/scGAEGAT/Klein.csv --split space --cellheadflag False --cellcount 2717

python Preprocessing_benchmark.py --inputfile /Users/wangjue/workspace/scGAEGAT/Data/benchmarkData/Zeisel/T2000_expression.txt --outputfile /Users/wangjue/workspace/scGAEGAT/Zeisel.csv --split space --cellheadflag False --cellcount 3005

2. generating sparse coding under data/

python Preprocessing_main.py --expression-name Chung --featureDir /Users/wangjue/workspace/scGAEGAT/
Clustering on Benchmarks

python3 -W ignore main_benchmark.py --datasetName Chung --benchmark /Users/wangjue/workspace/scGAEGAT/Data/benchmarkData/Chung/Chung_cell_label.csv --LTMGDir /Users/wangjue/workspace/scGAEGAT/Data/benchmarkData/ --regulized-type LTMG --EMtype celltypeEM --clustering-method LouvainK --useGAEembedding --npyDir outputDir_gpu/ --debuginfo  


Imputation on Benchmarks

Default: 10% of the non-zeros are flipped

python3 -W ignore main_benchmark.py --datasetName Chung --benchmark /Users/wangjue/workspace/scGAEGAT/Data/benchmarkData/Chung
