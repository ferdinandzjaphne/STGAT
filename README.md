# STGAT
Paper STGAT: Spatial-Temporal Graph Attention Networks for Traffic Flow Forecasting


## Data
data root are available at [Google Drive](https://drive.google.com/drive/folders/101kElpc2XudMpW_0v0CBpiZ5VPeeF5py?usp=sharing)


## Citation

If you find this repository, e.g., the code and the datasets, useful in your research, please cite the following paper:
```
@article{kong2020stgat,
  title={STGAT: Spatial-temporal graph attention networks for traffic flow forecasting},
  author={Kong, Xiangyuan and Xing, Weiwei and Wei, Xiang and Bao, Peng and Zhang, Jian and Lu, Wei},
  journal={IEEE Access},
  volume={8},
  pages={134363--134372},
  year={2020},
  publisher={IEEE}
}
```
python train.py --data='data/urban-core/' --adj_filename='data/urban-core/adj_generate.pkl' --num_of_vertices=304 --num_of_features=1 --module='urban-core' --params_dir='model-urban-core' --cuda=true
python testing.py --data='data/urban-core/' --adj_filename='data/urban-core/adj_generate.pkl' --num_of_vertices=304 --num_of_features=1 --cuda=true

python train.py --data='data/urban-mix/' --adj_filename='data/urban-mix/adj_generate.pkl' --num_of_vertices=1007 --num_of_features=1 --module='urban-mix' --params_dir='model-urban-mix'
python testing.py --data='data/urban-core/' --adj_filename='data/urban-mix/adj_generate.pkl' --num_of_vertices=1007 --num_of_features=1