import torch
import torch.utils.data
import numpy as np
import json
#from skimage import io
#from skimage import draw
#import skimage.transform as sktransform
import os
import math
from utils.crop_transform import CropTransform
from utils import augmentation
from collections import defaultdict
import timeit

import cv2

IAIN_CATCH=['131','131_2','132','133','193','194','197','200']

def collate(batch):

    ##tic=timeit.default_timer()
    batch_size = len(batch)
    imgs = []
    max_h=0
    max_w=0
    label_sizes = defaultdict(list)
    largest_label = {}
    for b in batch:
        if b is None:
            continue
        imgs.append(b["img"])
        max_h = max(max_h,b["img"].size(2))
        max_w = max(max_w,b["img"].size(3))
        for name,gt in b['sol_eol_gt'].items():
            if gt is None:
                label_sizes[name].append(0)
                #print('b {}, {}: {}    None'.format(len(label_sizes[name])-1, name, label_sizes[name][-1]))
            else:
                label_sizes[name].append(gt.size(1)) 
                #print('b {}, {}: {}    {}'.format(len(label_sizes[name])-1, name, label_sizes[name][-1],gt.size()))
    for name in b['sol_eol_gt']:
        largest_label[name] = max(label_sizes[name])

    if len(imgs) == 0:
        return None
    ##print(' col channels: {}'.format(len(imgs[0].size())))
    batch_size = len(imgs)

    resized_imgs = []
    for img in imgs:
        if img.size(2)<max_h or img.size(3)<max_w:
            resized = torch.zeros([1,img.size(1),max_h,max_w]).type(img.type())
            diff_h = max_h-img.size(2)
            pos_r = 0#np.random.randint(0,diff_h+1)
            diff_w = max_w-img.size(3)
            pos_c = 0#np.random.randint(0,diff_w+1)
            #if len(img.size())==3:
                #    resized[:,pos_r:pos_r+img.size(1), pos_c:pos_c+img.size(2)]=img
            #else:
                #    resized[pos_r:pos_r+img.size(1), pos_c:pos_c+img.size(2)]=img
            resized[:,:,pos_r:pos_r+img.size(2), pos_c:pos_c+img.size(3)]=img
            resized_imgs.append(resized)
        else:
            resized_imgs.append(img)

    labels = {}
    for name,count in largest_label.items():
        if count != 0:
            labels[name] = torch.zeros(batch_size, count, 4)
        else:
            labels[name]=None
    for i, b in enumerate(batch):
        for name,gt in b['sol_eol_gt'].items():
            if label_sizes[name][i] == 0:
                continue
            #if gt is None:
            #    ##print('n {}, {}: {}    None'.format(i, name, label_sizes[name][i]))
            #else:
            #    ##print('n {}, {}: {}    {}'.format(i, name, label_sizes[name][i],gt.size()))
            labels[name][i, :label_sizes[name][i]] = gt

    imgs = torch.cat(resized_imgs)

    ##print('collate: '+str(timeit.default_timer()-tic))
    return {
        'sol_eol_gt': labels,
        'img': imgs,
        "label_sizes": label_sizes
    }


class FormsDetect(torch.utils.data.Dataset):
    """
    Class for reading forms dataset and creating starting and ending gt
    """


    def __init__(self, dirPath=None, split=None, config=None, images=None):
        #if 'augmentation_params' in config['data_loader']:
        #    self.augmentation_params=config['augmentation_params']
        #else:
        #    self.augmentation_params=None
        self.cropToPage=config['crop_to_page']
        #patchSize=config['patch_size']
        if 'crop_params' in config:
            self.transform = CropTransform(config['crop_params'])
        else:
            self.transform = None
        self.rescale_range = config['rescale_range']
        if 'cache_resized_images' in config:
            self.cache_resized = config['cache_resized_images']
            self.cache_path = os.path.join(dirPath,'cache_'+str(self.rescale_range[1]))
            if self.cache_resized and not os.path.exists(self.cache_path):
                os.mkdir(self.cache_path)
        else:
            self.cache_resized = False
        if 'only_types' in config:
            self.only_types = config['only_types']
        else:
            self.only_types=None

        if images is not None:
            self.images=images
        else:
            with open(os.path.join(dirPath,'train_valid_test_split.json')) as f:
                #if split=='valid' or split=='validation':
                #    trainTest='train'
                #else:
                #    trainTest=split
                groupsToUse = json.loads(f.read())[split]
            self.images=[]
            for groupName, imageNames in groupsToUse.items():
                if groupName in IAIN_CATCH:
                    print('Skipped group {} as Iain has incomplete GT here'.format(groupName))
                    continue
                for imageName in imageNames:
                    org_path = os.path.join(dirPath,'groups',groupName,imageName)
                    if self.cache_resized:
                        path = os.path.join(self.cache_path,imageName)
                    else:
                        path = org_path
                    jsonPath = org_path[:org_path.rfind('.')]+'.json'
                    #print(jsonPath)
                    if os.path.exists(jsonPath):
                        rescale=1.0
                        if self.cache_resized and not os.path.exists(path):
                            org_img = cv2.imread(org_path)
                            target_dim1 = self.rescale_range[1]
                            target_dim0 = int(org_img.shape[0]/float(org_img.shape[1]) * target_dim1)
                            resized = cv2.resize(org_img,(target_dim1, target_dim0), interpolation = cv2.INTER_CUBIC)
                            cv2.imwrite(path,resized)
                            rescale = target_dim1/float(org_img.shape[1])
                        elif self.cache_resized:
                            with open(os.path.join(jsonPath) as f:
                                annotations = json.loads(f.read())
                            imW = annotations['width']

                            target_dim1 = self.rescale_range[1]
                            rescale = target_dim1/float(imW)

                        self.images.append({'id':imageName, 'imagePath':path, 'annotationPath':jsonPath, 'rescaled':rescale})
                            
                        # with open(path+'.json') as f:
                        #    annotations = json.loads(f.read())
                        #    imH = annotations['height']
                        #    imW = annotations['width']
                        #    #startCount=len(self.instances)
                        #    for bb in annotations['textBBs']:
        
        if 'no_blanks' in config:
            self.no_blanks = config['no_blanks']
        else:
            self.no_blanks = False
        if 'no_print_fields' in config:
            self.no_print_fields = config['no_print_fields']
        else:
            self.no_print_fields = False
        



    def __len__(self):
        return len(self.images)

    def __getitem__(self,index):
        ##ticFull=timeit.default_timer()
        imagePath = self.images[index]['imagePath']
        annotationPath = self.images[index]['annotationPath']
        rescaled = self.images[index]['rescaled']
        with open(annotationPath) as annFile:
            annotations = json.loads(annFile.read())

        ##tic=timeit.default_timer()
        org_img = cv2.imread(imagePath)#/255.0
        ##print('imread: {}  [{}, {}]'.format(timeit.default_timer()-tic,org_img.shape[0],org_img.shape[1]))
        ##print('       channels : {}'.format(len(org_img.shape)))
        if self.cropToPage:
            pageCorners = annotations['page_corners']
            xl = max(0,int(min(pageCorners['tl'],pageCorners['bl'])))
            xr = min(org_img.shape[1]-1,int(max(pageCorners['tr'],pageCorners['br'])))
            yt = max(0,int(min(pageCorners['tl'],pageCorners['tr'])))
            yb = min(org_img.shape[0]-1,int(max(pageCorners['bl'],pageCorners['br'])))
            org_img = org_img[yt:yb+1,xl:xr+1,:]
        target_dim1 = int(np.random.uniform(self.rescale_range[0], self.rescale_range[1]))
        s = target_dim1 / float(org_img.shape[1])
        s *= rescaled
        #print(s)
        target_dim0 = int(org_img.shape[0]/float(org_img.shape[1]) * target_dim1)
        ##tic=timeit.default_timer()
        org_img = cv2.resize(org_img,(target_dim1, target_dim0), interpolation = cv2.INTER_CUBIC)
        ##print('resize: {}  [{}, {}]'.format(timeit.default_timer()-tic,org_img.shape[0],org_img.shape[1]))
        
        ##tic=timeit.default_timer()
        text_start_gt, text_end_gt = self.getStartEndGT(annotations['textBBs'],s)
        field_start_gt, field_end_gt = self.getStartEndGT(annotations['fieldBBs'],s,fields=True)
        ##print('getStartEndGt: '+str(timeit.default_timer()-tic))

        ##ticTr=timeit.default_timer()
        if self.transform is not None:
            out = self.transform({
                "img": org_img,
                "sol_eol_gt": {
                        "text_start_gt": text_start_gt,
                        "text_end_gt": text_end_gt,
                        "field_start_gt": field_start_gt,
                        "field_end_gt": field_end_gt
                        }
            })
            org_img = out['img']
            text_start_gt = out['sol_eol_gt']['text_start_gt']
            text_end_gt = out['sol_eol_gt']['text_end_gt']
            field_start_gt = out['sol_eol_gt']['field_start_gt']
            field_end_gt = out['sol_eol_gt']['field_end_gt']

            ##tic=timeit.default_timer()
            org_img = augmentation.apply_random_color_rotation(org_img)
            org_img = augmentation.apply_tensmeyer_brightness(org_img)
            ##print('augmentation: {}'.format(timeit.default_timer()-tic))
        ##print('transform: {}  [{}, {}]'.format(timeit.default_timer()-ticTr,org_img.shape[0],org_img.shape[1]))


        img = org_img.transpose([2,0,1])[None,...] #from [row,col,color] to [batch,color,row,col]
        img = img.astype(np.float32)
        img = torch.from_numpy(img)
        img = 1.0 - img / 128.0 #ideally the median value would be 0
        #img = 1.0 - img / 255.0 #this way ink is on, page is off
        
        text_start_gt = None if text_start_gt.shape[1] == 0 else torch.from_numpy(text_start_gt)
        text_end_gt = None if text_end_gt.shape[1] == 0 else torch.from_numpy(text_end_gt)
        field_start_gt = None if field_start_gt.shape[1] == 0 else torch.from_numpy(field_start_gt)
        field_end_gt = None if field_end_gt.shape[1] == 0 else torch.from_numpy(field_end_gt)

        ##print('__getitem__: '+str(timeit.default_timer()-ticFull))
        if self.only_types is None:
            return {
                "img": img,
                "sol_eol_gt": {
                        "text_start_gt": text_start_gt,
                        "text_end_gt": text_end_gt,
                        "field_start_gt": field_start_gt,
                        "field_end_gt": field_end_gt
                        }
                }
        else:
            gt={}
            for ent in self.only_types:
                if type(ent)==list:
                    toComb=[]
                    for inst in ent[1:]:
                        toComb.append(eval(inst))
                    comb = torch.cat(toComb,dim=1)
                    gt[ent[0]]=comb
                else:
                    gt[ent]=eval(ent)

            return {
                "img": img,
                "sol_eol_gt": gt
                }



    def getStartEndGT(self,bbs,s, fields=False):
        start_gt = np.zeros((1,len(bbs), 4), dtype=np.float32)
        end_gt = np.zeros((1,len(bbs), 4), dtype=np.float32)
        j=0
        for bb in bbs:
            if ( fields and (
                    (self.no_blanks and (bb['isBlank']=='blank' or bb['isBlank']==3)) or
                    (self.no_print_fields and (bb['isBlank']=='print' or bb['isBlank']==2)) )):
                continue
            tlX = bb['poly_points'][0][0]
            tlY = bb['poly_points'][0][1]
            trX = bb['poly_points'][1][0]
            trY = bb['poly_points'][1][1]
            brX = bb['poly_points'][2][0]
            brY = bb['poly_points'][2][1]
            blX = bb['poly_points'][3][0]
            blY = bb['poly_points'][3][1]

            lX = (tlX+blX)/2.0
            lY = (tlY+blY)/2.0
            rX = (trX+brX)/2.0
            rY = (trY+brY)/2.0
            d=math.sqrt((lX-rX)**2 + (lY-rY)**2)

            hl = ((tlX-lX)*-(rY-lY) + (tlY-lY)*(rX-lX))/d #projection of half-left edge onto transpose horz run
            hr = ((brX-rX)*-(lY-rY) + (brY-rY)*(lX-rX))/d #projection of half-right edge onto transpose horz run
            h = (hl+hr)/2.0

            tX = lX + h*-(rY-lY)/d
            tY = lY + h*(rX-lX)/d
            bX = lX - h*-(rY-lY)/d
            bY = lY - h*(rX-lX)/d
            start_gt[:,j,0] = tX*s
            start_gt[:,j,1] = tY*s
            start_gt[:,j,2] = bX*s
            start_gt[:,j,3] = bY*s

            etX =tX + rX-lX
            etY =tY + rY-lY
            ebX =bX + rX-lX
            ebY =bY + rY-lY
            end_gt[:,j,0] = etX*s
            end_gt[:,j,1] = etY*s
            end_gt[:,j,2] = ebX*s
            end_gt[:,j,3] = ebY*s
            #if j<10:
            #    ##print('f {},{}   {},{}'.format(tX,tY,bX,bY))
            #    ##print('s {},{}   {},{}'.format(start_gt[:,j,0],start_gt[:,j,1],start_gt[:,j,2],start_gt[:,j,3]))
            j+=1
        return start_gt, end_gt

