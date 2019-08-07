gpu = '0'
random_seed = 0
trn_vid_path = '/ssd/GRID/lip_overlap/train'
val_vid_path = '/ssd/GRID/lip_overlap/val'
anno_path = '/ssd/GRID/GRID_align_txt'
vid_padding = 75
txt_padding = 200
base_lr = 1e-4
batch_size = 120
num_workers = 8
max_epoch = 10000
display = 10
test_step = 1000
save_prefix = 'weights/LipNet_overlap'
is_optimize = True