# -*- coding: utf-8 -*-
"""start of RF classifier (pandas df)

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1qFErhFs-pV_IAAtOlGt-uW8uMbI0OqwX
"""

!git clone -q https://github.com/fsiraj/Vegetation-Encroachment-on-Power-Infrastructure
  !mv ./Vegetation-Encroachment-on-Power-Infrastructure/* ./
  !rm -rf sample_data
  !rm -rf Vegetation-Encroachment-on-Power-Infrastructure

!pip install -q geopandas geemap

import ee
import geemap
import geopandas as gpd
import pandas as pd
import datetime

ee.Authenticate()

ee.Initialize()

saoMiguel = ee.Geometry.Point([-25.3425, 37.7532])
boundary = geemap.kml_to_ee('./study_area.kml').geometry()

"""# Cloud Masking

## Helpers
"""

def add_cloud_bands(img):
    # Get s2cloudless image, subset the probability band.
    cld_prb = ee.Image(img.get('s2cloudless')).select('probability')

    # Condition s2cloudless by the probability threshold value.
    is_cloud = cld_prb.gt(CLD_PRB_THRESH).rename('clouds')

    # Add the cloud probability layer and cloud mask as image bands.
    return img.addBands(ee.Image([cld_prb, is_cloud]))

def add_shadow_bands(img):
    # Identify water pixels from the SCL band.
    not_water = img.select('SCL').neq(6)

    # Identify dark NIR pixels that are not water (potential cloud shadow pixels).
    SR_BAND_SCALE = 1e4
    dark_pixels = img.select('B8').lt(NIR_DRK_THRESH*SR_BAND_SCALE).multiply(not_water).rename('dark_pixels')

    # Determine the direction to project cloud shadow from clouds (assumes UTM projection).
    shadow_azimuth = ee.Number(90).subtract(ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE')));

    # Project shadows from clouds for the distance specified by the CLD_PRJ_DIST input.
    cld_proj = (img.select('clouds').directionalDistanceTransform(shadow_azimuth, CLD_PRJ_DIST*10)
        .reproject(**{'crs': img.select(0).projection(), 'scale': 100})
        .select('distance')
        .mask()
        .rename('cloud_transform'))

    # Identify the intersection of dark pixels with cloud shadow projection.
    shadows = cld_proj.multiply(dark_pixels).rename('shadows')

    # Add dark pixels, cloud projection, and identified shadows as image bands.
    return img.addBands(ee.Image([dark_pixels, cld_proj, shadows]))

def add_cld_shdw_mask(img):
    # Add cloud component bands.
    img_cloud = add_cloud_bands(img)

    # Add cloud shadow component bands.
    img_cloud_shadow = add_shadow_bands(img_cloud)

    # Combine cloud and shadow mask, set cloud and shadow as value 1, else 0.
    is_cld_shdw = img_cloud_shadow.select('clouds').add(img_cloud_shadow.select('shadows')).gt(0)

    # Remove small cloud-shadow patches and dilate remaining pixels by BUFFER input.
    # 20 m scale is for speed, and assumes clouds don't require 10 m precision.
    is_cld_shdw = (is_cld_shdw.focal_min(2).focal_max(BUFFER*2/20)
        .reproject(**{'crs': img.select([0]).projection(), 'scale': 20})
        .rename('cloudmask'))

    # Add the final cloud-shadow mask to the image.
    return img_cloud_shadow.addBands(is_cld_shdw)

def apply_cld_shdw_mask(img):
    # Subset the cloudmask band and invert it so clouds/shadow are 0, else 1.
    not_cld_shdw = img.select('cloudmask').Not()

    # Subset reflectance bands and update their masks, return the result.
    return img.select('B.*').updateMask(not_cld_shdw)

"""## Parameters"""

AOI = saoMiguel
START_DATE = '2018-01-01'
END_DATE = '2021-07-30'
CLOUD_FILTER = 60
CLD_PRB_THRESH = 60
NIR_DRK_THRESH = 0.15
CLD_PRJ_DIST = 2
BUFFER = 10

"""## Build Sentinel-2 Collection"""

def get_s2_sr_cld_col(aoi, start_date, end_date):
    # Import and filter S2 SR.
    s2_sr_col = (ee.ImageCollection('COPERNICUS/S2_SR')
        .filterBounds(aoi)
        .filterDate(start_date, end_date))

    # Import and filter s2cloudless.
    s2_cloudless_col = (ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
        .filterBounds(aoi)
        .filterDate(start_date, end_date))

    # Join the filtered s2cloudless collection to the SR collection by the 'system:index' property.
    return ee.ImageCollection(ee.Join.saveFirst('s2cloudless').apply(**{
        'primary': s2_sr_col,
        'secondary': s2_cloudless_col,
        'condition': ee.Filter.equals(**{
            'leftField': 'system:index',
            'rightField': 'system:index'
        })
    }))

sen2 = get_s2_sr_cld_col(AOI, START_DATE, END_DATE)

"""#NDVI Bands and dataframe"""

import pandas as pd
import altair as alt
import numpy as np
import folium
import seaborn as sns

from sklearn.ensemble import RandomForestRegressor
reg = RandomForestRegressor()
reg.fit

from google.colab import drive
drive.mount('/content/drive')

collection = ee.ImageCollection(sen2).filterDate("2018-01-01", "2021-08-01")
point = {'type':'Point', 'coordinates':[-25.3511, 37.7623]};

info = collection.getRegion(point, 500).getInfo()

header = info[0]
data = np.array(info[1:])

iTime = header.index('time')
time = [datetime.datetime.fromtimestamp(i/1000) for i in (data[0:,iTime].astype(int))]

band_list = ['B1',u'B2']

iBands = [header.index(b) for b in band_list]
yData = data[0:,iBands].astype(np.float)

#Calculate NDVI
red = yData[:,0]
nir = yData[:,1]
ndvi = (nir - red) / (nir + red)

df = pd.DataFrame(data = ndvi, index =list(range(len(ndvi))), columns = ['B5'])
df = df.interpolate()
df['Date'] = pd.Series(time, index = df.index)
df = df.set_index(df.Date)
df.index = pd.to_datetime(df.index)
df['B5'] = df['B5'].fillna(0)

header

df.info()

df.describe()

sns.set(rc={'figure.figsize':(15, 6)})
df['B5'].plot(linewidth = 0.5)

import subprocess
from IPython.display import Image
import ee, datetime
import pandas as pd
from pylab import *
import seaborn as sns
from matplotlib.pylab import rcParams
from statsmodels.tsa.seasonal import seasonal_decompose

X = data.drop(['B5'], axis = 1)
y = data['B5']
