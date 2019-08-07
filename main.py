import torch
import torch.nn as nn
import torch.nn.init as init
import torch.nn.functional as F
from torch.utils.data import DataLoader
import math
import os
import sys
from dataset import MyDataset
import numpy as np
import time
from model import LipNet
import torch.optim as optim
import re
import json
from tensorboardX import SummaryWriter


if(__name__ == '__main__'):
    opt = __import__('options')
    writer = SummaryWriter()

def dataset2dataloader(dataset, num_workers=opt.num_workers):
    return DataLoader(dataset,
        batch_size = opt.batch_size, 
        shuffle = True,
        num_workers = num_workers,
        drop_last = False)

def show_lr(optimizer):
    lr = []
    for param_group in optimizer.param_groups:
        lr += [param_group['lr']]
    return np.array(lr).mean()    

def test(model, net):

    with torch.no_grad():
        dataset = MyDataset(opt.val_vid_path,
            opt.anno_path,
            opt.vid_padding,
            opt.txt_padding,
            'test')
        
        model.eval()
        loader = dataset2dataloader(dataset)
        loss_list = []
        wer = []
        crit = nn.CTCLoss()
        tic = time.time()
        for (i_iter, input) in enumerate(loader):            
            vid = input.get('vid').cuda()
            txt = input.get('txt').cuda()
            vid_len = input.get('vid_len').cuda()
            txt_len = input.get('txt_len').cuda()
            
            y = net(vid)
            loss = crit(y.transpose(0, 1), txt, vid_len.view(-1), txt_len.view(-1)).detach().cpu().numpy()
            loss_list.append(loss)
            pred_txt = y.argmax(-1)
            pred_txt = [MyDataset.ctc_arr2txt(pred_txt[_], start=1) for _ in range(pred_txt.size(0))]
            truth_txt = [MyDataset.arr2txt(txt[_], start=1) for _ in range(txt.size(0))]
            wer.append(MyDataset.wer(pred_txt, truth_txt))            
            if(i_iter % opt.display == 0):
                v = 1.0*(time.time()-tic)/(i_iter+1)
                eta = v * (len(loader)-i_iter) / 3600.0
                
                print(''.join(101*'-'))                
                print('{:<50}|{:>50}'.format('predict', 'truth'))
                print(''.join(101*'-'))                
                for (predict, truth) in list(zip(pred_txt, truth_txt))[:10]:
                    print('{:<50}|{:>50}'.format(predict, truth))                
                print(''.join(101 *'-'))
                print('test_iter={},eta={},wer={}'.format(i_iter,eta,np.array(wer).mean()))                
                print(''.join(101 *'-'))
                
        return (np.array(loss_list).mean(), np.array(wer).mean())
    
def train(model, net):
    
    dataset = MyDataset(opt.trn_vid_path,
        opt.anno_path,
        opt.vid_padding,
        opt.txt_padding,
        'train')
        
    loader = dataset2dataloader(dataset) 
    optimizer = optim.Adam(model.parameters(),
                lr = opt.base_lr,
                weight_decay = 0.,
                amsgrad = True)
                
    print('num_data:{}'.format(len(dataset.data)))    
    crit = nn.CTCLoss()
    tic = time.time()
    
    for epoch in range(opt.max_epoch):
        train_wer = []
        for (i_iter, input) in enumerate(loader):
            model.train()
            vid = input.get('vid').cuda()
            txt = input.get('txt').cuda()
            vid_len = input.get('vid_len').cuda()
            txt_len = input.get('txt_len').cuda()
            
            optimizer.zero_grad()
            y = net(vid)
            loss = crit(y.transpose(0, 1), txt, vid_len.view(-1), txt_len.view(-1))
            if(opt.is_optimize):
                loss.backward()
                optimizer.step()
            
            tot_iter = i_iter + epoch*len(loader)
            
            pred_txt = y.argmax(-1)
            pred_txt = [MyDataset.ctc_arr2txt(pred_txt[_], start=1) for _ in range(pred_txt.size(0))]
            truth_txt = [MyDataset.arr2txt(txt[_], start=1) for _ in range(txt.size(0))]
            train_wer.append(MyDataset.wer(pred_txt, truth_txt))
            
            if(tot_iter % opt.display == 0):
                v = 1.0*(time.time()-tic)/(tot_iter+1)
                eta = (len(loader)-i_iter)*v/3600.0
                
                writer.add_scalar('train loss', loss, tot_iter)
                writer.add_scalar('train wer', np.array(train_wer).mean(), tot_iter)              
                print(''.join(101*'-'))                
                print('{:<50}|{:>50}'.format('predict', 'truth'))                
                print(''.join(101*'-'))                
                
                for (predict, truth) in list(zip(pred_txt, truth_txt))[:3]:
                    print('{:<50}|{:>50}'.format(predict, truth))
                print(''.join(101*'-'))                
                print('epoch={},tot_iter={},eta={},loss={},train_wer={}'.format(epoch, tot_iter, eta, loss, np.array(train_wer).mean()))
                print(''.join(101*'-'))
                if(not opt.is_optimize):
                    break
                
            if(tot_iter % opt.test_step == 0):                
                (loss, wer) = test(model, net)
                print('i_iter={},lr={},loss={},wer={}'
                    .format(tot_iter,show_lr(optimizer),loss,wer))
                writer.add_scalar('val loss', loss, tot_iter)                    
                writer.add_scalar('wer', wer, tot_iter)
                savename = '{}_{}_{}.pt'.format(opt.save_prefix, loss, wer)
                (path, name) = os.path.split(savename)
                if(not os.path.exists(path)): os.makedirs(path)
                torch.save(model.state_dict(), savename)
                
if(__name__ == '__main__'):
    print("Loading options...")
    os.environ['CUDA_VISIBLE_DEVICES'] = opt.gpu    
    model = LipNet()
    model = model.cuda()
    net = nn.DataParallel(model).cuda()

    if(hasattr(opt, 'weights')):
        pretrained_dict = torch.load(opt.weights)
        model_dict = model.state_dict()
        pretrained_dict = {k: v for k, v in pretrained_dict.items() if k in model_dict.keys() and v.size() == model_dict[k].size()}
        missed_params = [k for k, v in model_dict.items() if not k in pretrained_dict.keys()]
        print('loaded params/tot params:{}/{}'.format(len(pretrained_dict),len(model_dict)))
        print('miss matched params:{}'.format(missed_params))
        model_dict.update(pretrained_dict)
        model.load_state_dict(model_dict)
        
    torch.manual_seed(opt.random_seed)
    torch.cuda.manual_seed_all(opt.random_seed)
    train(model, net)
        