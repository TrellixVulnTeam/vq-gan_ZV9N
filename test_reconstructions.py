import io
import requests
import PIL
from PIL import Image
from PIL import ImageDraw, ImageFont
import numpy as np
import yaml
import torch
from omegaconf import OmegaConf
from taming.models.vqgan import VQModel, GumbelVQ

import torchvision.transforms as T
import torchvision.transforms.functional as TF

font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf", 22)

def download_image(url):
    resp = requests.get(url)
    resp.raise_for_status()
    return PIL.Image.open(io.BytesIO(resp.content))

def preprocess(img, target_image_size=256):
    s = min(img.size)
    
    if s < target_image_size:
        raise ValueError(f'min dim for image {s} < {target_image_size}')
        
    r = target_image_size / s
    s = (round(r * img.size[1]), round(r * img.size[0]))
    img = TF.resize(img, s, interpolation=PIL.Image.LANCZOS)
    img = TF.center_crop(img, output_size=2 * [target_image_size])
    img = torch.unsqueeze(T.ToTensor()(img), 0)
    return img

def stack_reconstructions(input, x0, x1, x2, titles=[]):
  assert input.size == x1.size
  w, h = input.size[0], input.size[1]
  img = Image.new("RGB", (4*w, h))
  img.paste(input, (0,0))
  img.paste(x0, (1*w,0))
  img.paste(x1, (2*w,0))
  img.paste(x2, (3*w,0))

  for i, title in enumerate(titles):
    ImageDraw.Draw(img).text((i*w, 0), f'{title}', (255, 255, 255), font=font)  # coordinates, text, color, font
  img.save("input_reconstructions.jpg")

def load_config(config_path, display=False):
  config = OmegaConf.load(config_path)
  if display:
    print(yaml.dump(OmegaConf.to_container(config)))
  return config

def load_vqgan(config, ckpt_path=None, is_gumbel=False):
  if is_gumbel:
    model = GumbelVQ(**config.model.params)
  else:
    model = VQModel(**config.model.params)
  if ckpt_path is not None:
    sd = torch.load(ckpt_path, map_location="cpu")["state_dict"]
    missing, unexpected = model.load_state_dict(sd, strict=False)
  return model.eval()

def preprocess_vqgan(x):
  x = 2.*x - 1.
  return x

def custom_to_pil(x):
  x = x.detach().cpu()
  x = torch.clamp(x, -1., 1.)
  x = (x + 1.)/2.
  x = x.permute(1,2,0).numpy()
  x = (255*x).astype(np.uint8)
  x = Image.fromarray(x)
  if not x.mode == "RGB":
    x = x.convert("RGB")
  return x

def reconstruct_with_vqgan(x, model):
  # could also use model(x) for reconstruction but use explicit encoding and decoding here
  z, _, [_, _, indices] = model.encode(x)
  print(f"VQGAN --- {model.__class__.__name__}: latent shape: {z.shape[2:]}")
  print("z.max(), z.min():", z.max(), z.min())
  print("indices.shape, indices.max(), indices.min():", indices.shape, indices.max(), indices.min())
  xrec = model.decode(z)
  return xrec

def reconstruction_pipeline(url, size=256):
  x_vqgan = preprocess(download_image(url), target_image_size=size)
  x_vqgan = x_vqgan.to("cuda:0")
  
  print(f"input is of size: {x_vqgan.shape}")
  x0 = reconstruct_with_vqgan(preprocess_vqgan(x_vqgan), model32x32)
  x1 = reconstruct_with_vqgan(preprocess_vqgan(x_vqgan), model16384)
  x2 = reconstruct_with_vqgan(preprocess_vqgan(x_vqgan), modelsaycam)
  img = stack_reconstructions(custom_to_pil(preprocess_vqgan(x_vqgan[0])), custom_to_pil(x0[0]), custom_to_pil(x1[0]), custom_to_pil(x2[0]), titles=titles)

  return img

if __name__ == "__main__":
    config16384 = load_config("logs/vqgan_imagenet_f16_16384/configs/model.yaml", display=False)
    model16384 = load_vqgan(config16384, ckpt_path="logs/vqgan_imagenet_f16_16384/checkpoints/last.ckpt").to("cuda:0")

    config32x32 = load_config("logs/vqgan_gumbel_f8/configs/model.yaml", display=False)
    model32x32 = load_vqgan(config32x32, ckpt_path="logs/vqgan_gumbel_f8/checkpoints/last.ckpt", is_gumbel=True).to("cuda:0")

    configsaycam = load_config("logs/2022-08-07T20-31-31_custom_vqgan_32x32/configs/2022-08-09T20-37-58-project.yaml", display=False)
    modelsaycam = load_vqgan(configsaycam, ckpt_path="logs/2022-08-07T20-31-31_custom_vqgan_32x32/checkpoints/last.ckpt").to("cuda:0")

    titles=["Input", "OpenImgs (f8, 8192)", "OpenImgs (f16, 16384)", "SAYCam (f8, 8192)"]
    reconstruction_pipeline(url='https://heibox.uni-heidelberg.de/f/7bb608381aae4539ba7a/?dl=1', size=256)
