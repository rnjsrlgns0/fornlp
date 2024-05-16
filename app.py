import streamlit as st
from streamlit_folium import st_folium
from shapely.geometry import Point, MultiPolygon, Polygon, MultiLineString,MultiPoint

import os
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from tqdm import tqdm

import folium 
from folium.features import DivIcon 

import urllib.request
import urllib.parse
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote_plus    
from urllib.request import urlretrieve
import requests
import xmltodict
import json

api_key = st.text_input('key를 입력하세요: ')
#### pnu 수집
poi = st.text_input('원하는 장소의 정확한 지번주소를 넣어주세요, ex) 경기도 시흥시 은행동 599-1, 경기도 시흥시 은행동 599-2:  ')
li_poi = poi.split(', ')
li_pnu = []

# '----------------법정동 코드 불러오기--------------'
df_lesi = pd.read_csv('./code.txt', sep='\t')
df_lesi = df_lesi.loc[df_lesi['폐지여부'] == '존재']


# '----------------함수 정의--------------'
#필요 함수 정의
def get_data(key, pnuCode):
    """
    연속지적도

    종류: 2D 데이터API 2.0
    분류: 토지
    서비스명: 연속지적도
    서비스ID: LP_PA_CBND_BUBUN
    제공처: 국토교통부
    버전: 1.0
    - key: Vworld Open API 인증키
    - pnuCode: PNU코드 19자리
    """
    # 엔드포인트
    endpoint = "http://api.vworld.kr/req/data"

    # 요청 파라미터
    service = "data"
    request = "GetFeature"
    data = "LP_PA_CBND_BUBUN"
    page = 1
    size = 1000
    attrFilter = f"pnu:=:{pnuCode}"

    # 요청 URL
    url = f"{endpoint}?service={service}&request={request}&data={data}&key={key}&attrFilter={attrFilter}&page={page}&size={size}"
    # 요청 결과
    res = json.loads(requests.get(url).text)
    # GeoJson 생성
    featureCollection = res["response"]["result"]["featureCollection"]

    return featureCollection

#'읍면동'인 경우와 '리'인 경우를 나누어야함
#읍면동인 경우 법정동코드 앞 8자리 가져온 후 뒤에 '00'을 추가
#리인 경우 법정동코드 앞 10자리 

def get_pnu(txt):
    #txt는 정식 지번 주소
    # 법정동 추출
    adm = ' '.join(txt.split(' ')[:-1])
    if adm[-1] != '리':
        adm_cd = str(df_lesi.loc[df_lesi['법정동명'].str.contains(adm),'법정동코드'].values)[1:9]
        adm_cd = f'{adm_cd}00'
    else:
        adm_cd = str(df_lesi.loc[df_lesi['법정동명'].str.contains(adm),'법정동코드'].values)[1:-1]

    # 본번 및 지목구분 추출
    bonbun, *rest = txt.split(' ')[-1].split('-')
    gubun = '2' if '산' in bonbun else '1'
    bonbun = bonbun.strip('산').zfill(4)

    # 부번추출
    bubun = rest[0].zfill(4) if rest else '0000'
    return adm_cd + gubun + bonbun + bubun

def calculate_centroid(polygon):
    x_sum = 0
    y_sum = 0
    num_points = 0

    for polygon in polygon:
        for ring in polygon:
            for point in ring:
                x_sum += point[0]
                y_sum += point[1]
                num_points += 1

    centroid_x = x_sum / num_points
    centroid_y = y_sum / num_points

    return centroid_x, centroid_y

#위, 경도 좌표와 용도지역 검색용 중심점 생성함수
def calculate_centroid_test(poly):
    centroid = poly.centroid
    x = centroid.x
    y = centroid.y
    # 폴리곤 내부에 중심점이 있는지 확인
    if poly.contains(centroid):
        # 중심점이 폴리곤 내부에 있으면 그대로 사용
        point_inside_poly = centroid
    else:
        # 중심점이 폴리곤 외부에 있으면 폴리곤 내부의 가장 가까운 점으로 이동
        nearest_point_inside_poly, _ = nearest_points(poly, centroid)
        point_inside_poly = nearest_point_inside_poly
    s_t = str(point_inside_poly).split('(')
    s1 = s_t[0].strip(' ').lower()
    s2 = s_t[1]
    geom = '('.join([s1,s2])
    return x, y, geom

def get_prps(key, geom):
    """
    연속지적도

    종류: 2D 데이터API 2.0
    분류: 토지
    서비스명: 연속지적도
    서비스ID: LP_PA_CBND_BUBUN
    제공처: 국토교통부
    버전: 1.0
    - key: Vworld Open API 인증키
    - pnuCode: PNU코드 19자리
    """
    # 엔드포인트
    endpoint = "http://api.vworld.kr/req/data"
    # endpoint = "https://api.vworld.kr/ned/data/getLandUseAttr"   
    # 요청 파라미터
    service = "data"
    request = "GetFeature"
    data = "LT_C_UQ111"
    page = 1
    geomFilter = geom
    size = 1000

    # 요청 URL
    url = f"{endpoint}?service={service}&request={request}&data={data}&key={key}&geomfilter={geomFilter}&page={page}&size={size}"
    # 요청 결과
    res = json.loads(requests.get(url).text)
    # GeoJson 생성
    featureCollection = res['response']['result']['featureCollection']['features'][0]['properties']

    # return featureCollection
    return featureCollection

# '----------------데이터 프레임 및 폴리움 지도 생성--------------'

# '----------------데이터 프레임 및 폴리움 지도 생성--------------'
region_nm = ' '.join(li_poi[0].split(' ')[:-1])
for i in li_poi:
    if len(i.split(' ')) > 3:
        i = i
    else:
        i = region_nm + ' ' + i
    li_pnu.append(get_pnu(i))

#중심점 좌표를 통한 배경지도 가져오기
pnu_center = li_pnu[len(li_pnu)//2]
#중심점 구하기
polygon_center = MultiPolygon(get_data(api_key, pnu_center)['features'][0]['geometry']['coordinates'])
x_c, y_c, _ = calculate_centroid_test(polygon_center)


tiles = "http://mt0.google.com/vt/lyrs=s&hl=ko&x={x}&y={y}&z={z}"
# 속성 설정
attr = "Google"

# folium 지도 생성하기
m = folium.Map(
    location=[y_c, x_c],
    zoom_start=22,
    tiles = tiles,
    attr = attr
)
df = pd.DataFrame(columns=['지번주소', '공시지가', '지목', 'area', '토지이용계획'],
                  index = range(1, len(li_pnu)+1)) #index 1번부터 나가게 조정 토지 위 마커와 일치해야함

#리턴되지 않는 주소 모음
li_error = []

# 수집한 pnu로 geometry 가져오기
for i, j in zip(li_pnu, range(1,len(li_pnu)+1)):
    try: 
        geo = get_data(api_key,i)
        geo_center =  MultiPolygon(geo['features'][0]['geometry']['coordinates'])
        # x_c_1, y_c_1 = calculate_centroid(geo_center)
        x_c_1, y_c_1, _ = calculate_centroid_test(geo_center)
        geo_plan = get_prps(api_key, _)


        folium.map.Marker([y_c_1, x_c_1],
                            icon = DivIcon(
                                    icon_size = (20, 20),
                                    html = f'<div style = "font-size: 12pt; font-weight: bold; color: white;">{j}</div>'                                  
                            )
                            ).add_to(m)
        folium.GeoJson(data=geo,
                    name="geojson",
                    tooltip=folium.GeoJsonTooltip(fields=('pnu', 'addr', 'jibun','jiga','gosi_year','gosi_month'),
                                                    aliases=('PNU코드', '주소','지번/지목','공시지가','기준연도','기준월'))
                    ).add_to(m)
        addr = geo['features'][0]['properties']['addr'] # 지자체명 포함 지번주소
        try:
            jiga = format(int(geo['features'][0]['properties']['jiga']),',')+'원' # 최신공시지가
        except:
            jiga = geo['features'][0]['properties']['jiga']
        prps = geo['features'][0]['properties']['jibun'][-1]

        plan = geo_plan['uname']

        df.loc[j, '토지이용계획'] = plan
        df.loc[j,'지번주소'] = addr
        df.loc[j,'공시지가'] = jiga
        df.loc[j,'지목'] = prps
    except:
        li_error.append(i)
        pass

# call to render Folium map in Streamlit

# '----------------데이터 프레임 생성--------------'
df = df.loc[~df['공시지가'].isna()]
st.table(df)

# '----------------지도 생성--------------'
st_data = st_folium(m, width=1450)

