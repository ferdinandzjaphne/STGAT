import time
import util
import torch
import torch.nn as nn
import torch.nn.functional as F
import argparse
import numpy as np
from model.stgat import STGAT
from loss.MSELoss import mse_loss
from loss.MAPELoss import MAPELoss
from torch.utils.tensorboard import SummaryWriter
import logging
import os
import sys

parser = argparse.ArgumentParser()
# parser.add_argument('--graph_signal_matrix_filename', type=str, default='data/METR-LA/data2.npz')
parser.add_argument('--data', type=str, default='data/METR-LA/')
parser.add_argument('--adj_filename', type=str, default='data/METR-LA/adj_mx_dijsk.pkl')
parser.add_argument('--params_dir', type=str, default='experiment_METR_LA')
parser.add_argument('--num_of_vertices', type=int, default=207)
parser.add_argument('--num_of_features', type=int, default=2)
parser.add_argument('--points_per_hour', type=int, default=12)
parser.add_argument('--num_for_predict', type=int, default=12)
parser.add_argument('--num_of_weeks', type=int, default=1)
parser.add_argument('--num_of_days', type=int, default=1)
parser.add_argument('--num_of_hours', type=int, default=1)
parser.add_argument('--batch_size', type=int, default=100)
parser.add_argument('--epoch', type=int, default=500)
parser.add_argument('--lr', type=float, default=1e-3)
parser.add_argument('--print_every', type=float, default=200)
parser.add_argument('--opt', type=str, default='adam')
parser.add_argument('--graph', type=str, default='default')
parser.add_argument('--adjtype', type=str, default='symnadj')
parser.add_argument('--early_stop_maxtry', type=int, default=20)
parser.add_argument('--module_name', type=str, default='urban-core')
parser.add_argument('--cuda', action='store_true', help='use CUDA training.')

args = parser.parse_args()

args.cuda = args.cuda and torch.cuda.is_available()
print(f'Training configs: {args}')


def weight_schedule(epoch, max_val=10, mult=-5, max_epochs=100):
    if epoch == 0:
        return 0.
    w = max_val * np.exp(mult * (1. - float(epoch) / max_epochs) ** 2)
    w = float(w)
    if epoch > max_epochs:
        return max_val
    return w

def main():
    #set seed
    #torch.manual_seed(args.seed)
    #np.random.seed(args.seed)
    #load data
    sensor_ids, sensor_id_to_ind, adj_mx = util.load_adj(args.adj_filename, args.adjtype)
    # adj_mx = adj_mx[0]
    # for i in range(len(adj_mx)):
    #     for j in range(len(adj_mx[i])):
    #         if adj_mx[i][j] != adj_mx[j][i]:
    #             print("NOTSYM!")
    #             print(adj_mx[i][j], adj_mx[j][i])
    # return
    dataloader = util.load_dataset(args.data, args.batch_size, args.batch_size, args.batch_size)
    scaler = dataloader['scaler']
    # for i in range(args.num_of_vertices):
    #     adj_mx[0][i][i] = -9e15
    adj_mx = torch.from_numpy(np.array(adj_mx))[0]
    adj_mx_ = torch.from_numpy(np.random.permutation(np.array(adj_mx)))[0]
    # adj_mx = torch.ones_like(adj_mx)
    if args.cuda:
        adj_mx = adj_mx.cuda()
        adj_mx_ = adj_mx_.cuda()
    # zero_vec = -9e15*torch.ones_like(adj_mx)
    # adj_mx = torch.where(torch.isnan(adj_mx), zero_vec, adj_mx)
    # adj_mx = torch.where(adj_mx==0.0, zero_vec, adj_mx)
    # print(adj_mx)
    print('adj', adj_mx.shape)
    print(args)

    net = STGAT(args.cuda, args.num_of_vertices, args.num_of_features, args.points_per_hour*args.num_of_hours, args.num_for_predict)
    if args.cuda:
        net = net.cuda()
    
    # get optimizer
    optimizer = torch.optim.Adam(net.parameters(), lr=args.lr, betas=(0.9, 0.999), weight_decay=0)
    # optimizer = torch.optim.SGD(net.parameters(), lr=args.lr, momentum=0.9)
    lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=0.9)

    loss_function = nn.SmoothL1Loss()
    b_xent = nn.BCEWithLogitsLoss()

    run_id = 'stgat_%s_%d_%s/' % (args.module_name, args.batch_size, time.strftime('%m%d%H%M%S'))
    writer = SummaryWriter('runs/' + run_id)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    log_dir = os.path.join("logs", run_id)
    
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    file_handler = logging.FileHandler(os.path.join(log_dir, 'info.log'))
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    # Add google cloud log handler
    logger.info('Log directory: %s', run_id)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("start training...")
    his_loss =[]
    val_time = []
    train_time = []
    mmin_val_loss = 10000
    mmin_epoch = 10000
    trycnt = 0

    batches_seen = 0

    for i in range(args.epoch):
        
        # # Training
        net.train()
        train_loss = []
        train_mape = []
        train_rmse = []
        t1 = time.time()

        for iter, (trainx, trainy, trainx_) in enumerate(dataloader['train_loader']):
            optimizer.zero_grad()

            # batch_size = trainx.shape[0]
            # lbl_1 = torch.ones(batch_size, args.num_of_vertices)
            # lbl_2 = torch.zeros(batch_size, args.num_of_vertices)
            # lbl = torch.cat((lbl_1, lbl_2), 1)


            if args.cuda:
                trainx = trainx.cuda()
                trainy = trainy.cuda()
                trainx_ = trainx_.cuda()
                # lbl = lbl.cuda()
            # x shape (batch_size, num_nodes, num_of_hours, feature_dim)
            
            output, logits = net(adj_mx, trainx, adj_mx_, trainx_)
            
            # with torch.no_grad():
                # output2, logits = net(adj_mx, trainx, adj_mx, trainx_)
                # output2 = output2.permute(0, 3, 1, 2)
                # predict2 = scaler.inverse_transform(output2)

            real_val = trainy[:,0,:,:]
            real_val = torch.unsqueeze(real_val,dim=1)
            output = output.permute(0, 3, 1, 2)

            predict = scaler.inverse_transform(output)
            real = scaler.inverse_transform(real_val)
            # print('loss shape', real.shape, predict.shape)

            mae = util.masked_mae(predict, real, 0.0)
            mape = util.masked_mape(predict, real, 0.0).item()
            rmse = util.masked_rmse(predict, real, 0.0).item()
            # mape_loss = util.mape_loss(predict, real, 0.0)
            # rmsle = util.masked_rmsle(predict, real, args.cuda, 0.0)
            
            w = weight_schedule(i)
            # loss_semi = util.masked_mae(predict, predict2) * w
            # loss_semi_infomax = b_xent(logits, lbl) * w
            # loss = rmse + loss_semi_infomax + mae
            # loss = rmse + loss_semi_infomax
            # loss = mae + loss_semi_infomax
            loss = mae

            mae = mae.item()
            # rmse = rmse.item()
            # mape = mape.item()
            
            # print(mae, rmse, loss_semi_infomax.item())
            # loss = loss_function(predict, predict2, real)
            
            train_loss.append(mae)
            train_mape.append(mape)
            train_rmse.append(rmse)

            batches_seen += 1

            loss.backward()
            # torch.nn.utils.clip_grad_norm_(net.parameters(), 5)
            optimizer.step()

            
            if iter % args.print_every == 0 :
                log = 'Iter: {:03d}, Train Loss: {:.4f}, Train MAPE: {:.4f}, Train RMSE: {:.4f}'
                logger.info(log.format(iter, train_loss[-1], train_mape[-1], train_rmse[-1]))
            # if iter>10:
            #         break
            break

        
        t2 = time.time()
        train_time.append(t2-t1)

        with torch.no_grad():
            # Validation
            net.eval()
            valid_loss = []
            valid_mape = []
            valid_rmse = []
            s1 = time.time()
            for iter, (valx, valy) in enumerate(dataloader['val_loader']):
                if args.cuda:
                    valx = valx.cuda()
                    valy = valy.cuda()
                output = net(adj_mx, valx)

                real_val = valy[:,0,:,:]
                real_val = torch.unsqueeze(real_val,dim=1)
                output = output.permute(0, 3, 1, 2)
                predict = scaler.inverse_transform(output)
                real = scaler.inverse_transform(real_val)

                mae = util.masked_mae(predict, real, 0.0).item()
                mape = util.masked_mape(predict, real, 0.0).item()
                rmse = util.masked_rmse(predict, real, 0.0).item()
                valid_loss.append(mae)
                valid_mape.append(mape)
                valid_rmse.append(rmse)
                # if iter>10:
                #     break
                break

            s2 = time.time()
            log = 'Epoch: {:03d}, Inference Time: {:.4f} secs'
            logger.info(log.format(i,(s2-s1)))

            val_time.append(s2-s1)
            mtrain_loss = np.mean(train_loss)
            mtrain_mape = np.mean(train_mape)
            mtrain_rmse = np.mean(train_rmse)

            mvalid_loss = np.mean(valid_loss)
            mvalid_mape = np.mean(valid_mape)
            mvalid_rmse = np.mean(valid_rmse)
            his_loss.append(mvalid_loss)

            log = 'Epoch: {:03d}, Train Loss: {:.4f}, Train MAPE: {:.4f}, Train RMSE: {:.4f}, Valid Loss: {:.4f}, Valid MAPE: {:.4f}, Valid RMSE: {:.4f}, Training Time: {:.4f}/epoch'
            logger.info(log.format(i, mtrain_loss, mtrain_mape, mtrain_rmse, mvalid_loss, mvalid_mape, mvalid_rmse, (t2 - t1)))

            writer.add_scalar('Loss/Train_MAE', mtrain_loss, batches_seen)
            writer.add_scalar('Loss/Train_MAPE', mtrain_mape, batches_seen)
            writer.add_scalar('Loss/Train_RMSE', mtrain_rmse, batches_seen)

            writer.add_scalar('Loss/Val_MAE', mvalid_loss, batches_seen)
            writer.add_scalar('Loss/Val_MAPE', mvalid_mape, batches_seen)
            writer.add_scalar('Loss/Val_RMSE', mvalid_rmse, batches_seen)

            # lr_scheduler.step(mvalid_loss)
            # lr_scheduler.step()

            torch.save(net, os.path.join("models", args.params_dir+"_epoch_"+str(i)+"_"+str(round(mvalid_loss,2))+".pth"))
            if mmin_val_loss > mvalid_loss:
                mmin_val_loss = mvalid_loss
                mmin_epoch = i
                trycnt = 0

            # Testing
            outputs = []
            realy = []

            for iter, (testx, testy) in enumerate(dataloader['test_loader']):
                if args.cuda:
                    testx = testx.cuda()
                    testy = testy.cuda()
                output = net(adj_mx, testx)
                output = output.permute(0, 3, 1, 2)
                output = output.squeeze()

                outputs.append(output)
                realy.append(testy[:,0,:,:].squeeze())
                # if iter>10:
                #     break
            

            yhat = torch.cat(outputs, dim=0)
            realy = torch.cat(realy, dim=0)
            if args.cuda:
                yhat = yhat.cuda()
                realy = realy.cuda()

            logger.info("Training finished")

            amae = []
            amape = []
            armse = []
            for i in range(12):
                pred = scaler.inverse_transform(yhat[:,:,i])
                real = scaler.inverse_transform(realy[:,:,i])
                metrics = util.metric(pred,real)
                log = 'Evaluate best model on test data for horizon {:d}, Test MAE: {:.4f}, Test MAPE: {:.4f}, Test RMSE: {:.4f}'
                logger.info(log.format(i+1, metrics[0], metrics[1], metrics[2]))
                amae.append(metrics[0])
                amape.append(metrics[1])
                armse.append(metrics[2])

            saved_pred = pred
            saved_real = real

            
            log = 'On average over 12 horizons, Test MAE: {:.4f}, Test MAPE: {:.4f}, Test RMSE: {:.4f}'
            logger.info(log.format(np.mean(amae),np.mean(amape),np.mean(armse)))
            logger.info('early stop trycnt: .%d .%d', trycnt, mmin_epoch)
            logger.info('==================================================================================')
            logger.info('\r\n\r\n\r\n')

            
            for i in range(6):
                pred = scaler.inverse_transform(yhat[:,:,i])
                real = scaler.inverse_transform(realy[:,:,i])
                metrics = util.metric(pred,real)
                log = 'Evaluate best model on test data for horizon {:d}, Test MAE: {:.4f}, Test MAPE: {:.4f}, Test RMSE: {:.4f}'
                logger.info(log.format(i+1, metrics[0], metrics[1], metrics[2]))
                amae.append(metrics[0])
                amape.append(metrics[1])
                armse.append(metrics[2])

            
            log = 'On average over 6 horizons, Test MAE: {:.4f}, Test MAPE: {:.4f}, Test RMSE: {:.4f}'
            logger.info(log.format(np.mean(amae),np.mean(amape),np.mean(armse)))
            logger.info('early stop trycnt: .%d .%d', trycnt, mmin_epoch)
            logger.info('==================================================================================')
            logger.info('\r\n\r\n\r\n')
            
            
            for i in range(3):
                pred = scaler.inverse_transform(yhat[:,:,i])
                real = scaler.inverse_transform(realy[:,:,i])
                metrics = util.metric(pred,real)
                log = 'Evaluate best model on test data for horizon {:d}, Test MAE: {:.4f}, Test MAPE: {:.4f}, Test RMSE: {:.4f}'
                logger.info(log.format(i+1, metrics[0], metrics[1], metrics[2]))
                amae.append(metrics[0])
                amape.append(metrics[1])
                armse.append(metrics[2])

            
            log = 'On average over 3 horizons, Test MAE: {:.4f}, Test MAPE: {:.4f}, Test RMSE: {:.4f}'
            logger.info(log.format(np.mean(amae),np.mean(amape),np.mean(armse)))
            logger.info('early stop trycnt: .%d .%d', trycnt, mmin_epoch)
            logger.info('==================================================================================')
            logger.info('\r\n\r\n\r\n')

            
            # for early stop
            trycnt += 1
            if args.early_stop_maxtry < trycnt:
                data = {'prediction': saved_pred, 'truth': saved_real}
                np.savez_compressed('results/result_prediction.npz', **data)    
                print('early stop!')
                return


    logger.info("Average Training Time: {:.4f} secs/epoch".format(np.mean(train_time)))
    logger.info("Average Inference Time: {:.4f} secs".format(np.mean(val_time)))

if __name__ == "__main__":
    t1 = time.time()
    main()
    t2 = time.time()
    print("Total time spent: {:.4f}".format(t2-t1))