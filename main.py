import requests
from bs4 import BeautifulSoup as bs
import pandas as pd
import folium
from folium.plugins import MarkerCluster

# cookies data extracted from cURL for login data
cookies = {
    '__utma': '161274942.58113055.1719420471.1719420471.1719420471.1',
    '__utmb': '161274942.2.10.1719420471',
    '__utmc': '161274942',
    '__utmz': '161274942.1719420471.1.1.utmcsr=(direct)|utmccn=(direct)|utmcmd=(none)',
    'ckFirstPageLoad': 'yes',
    'ckPrevEmail': 'ephraim%40ephraimperfect%2Eco%2Euk',
    'ckPrevPWD': '16891689',
    '__utmt': '1',
    'ASPSESSIONIDACQDARTS': 'CDKBMMMBEGMNONLBEAHANOMP',
    'ckCookieNotice': '2018%2D01%2D01',
}

headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Sec-Fetch-Site': 'same-origin',
    # 'Cookie': '__utma=161274942.58113055.1719420471.1719420471.1719420471.1; __utmb=161274942.2.10.1719420471; __utmc=161274942; __utmz=161274942.1719420471.1.1.utmcsr=(direct)|utmccn=(direct)|utmcmd=(none); ckFirstPageLoad=yes; ckPrevEmail=ephraim%40ephraimperfect%2Eco%2Euk; ckPrevPWD=16891689; __utmt=1; ASPSESSIONIDACQDARTS=CDKBMMMBEGMNONLBEAHANOMP; ckCookieNotice=2018%2D01%2D01',
    # 'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.rarebirdalert.co.uk/v2/Content/index.aspx',
    'Sec-Fetch-Mode': 'navigate',
    'Host': 'www.rarebirdalert.co.uk',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
    'Accept-Language': 'en-GB,en;q=0.9',
    'Sec-Fetch-Dest': 'document',
    'Connection': 'keep-alive',
}

# parse the html content
response = requests.get('http://www.rarebirdalert.co.uk/RealData/rssnewsitems.asp', cookies=cookies, headers=headers).text
soup = bs(response, 'html.parser')

# Find the table element
table = soup.find('table', attrs = {"width" : "650"})

# Extract the data from the cells
data = []

for row in table.find_all('tr'):

   cols = row.find_all('td')

   # Extracting the table headers
   if len(cols) == 0:
       cols = row.find_all('th')

   cols = [ele.text.strip() for ele in cols]

   data.append([ele for ele in cols if ele])  # Get rid of empty values

# create pandas dataframe of content
df_na = pd.DataFrame(data, columns = ['data'])
new_df = df_na.dropna()

print(new_df)

# split bird data rows from info rows into 2 columns
df = pd.DataFrame({'data':new_df['data'].iloc[::2].values, 'Info':new_df['data'].iloc[1::2].values})

# split bird data into separate columns
split_data = df['data'].str.split(',', expand=True).rename(columns={0:'Bird',1:'Site',2:'County'})
split_bird = split_data['Bird'].str.split('  ', expand=True).rename(columns={0:'Time',1:'Bird'})

# concat all RBA data to one dataframe
complete_data = pd.concat([split_bird['Time'],split_bird['Bird'],split_data['Site'],split_data['County'],df['Info']], sort=False, axis=1)

# Only accept today's data
today_data = complete_data[~complete_data.Time.str.contains("Yesterday")]

# extract coordinate information from dataframe
coords = today_data['Info'].str.extract(r"(\-?(90|[0-8]?[0-9]\.[0-9]{0,6}))\,(\-?(180|(1[0-7][0-9]|[0-9]{0,2})\.[0-9]{0,6}))").rename(columns={0:'lat',1:'abs_lat',2:'lng',3:'abs_lng'})

# concat with coordinates
data_nan = pd.concat([today_data, coords['lat'], coords['lng']], sort=False, axis=1)
data_loc = data_nan.dropna()

# identify scarcity of species
bird_status = pd.read_csv('bird_status.csv')

# create map to mark locations on location is map centre, tiles is map style, and zoom_start is start zoom
m = folium.Map(location=[55.3781,-2], tiles='OpenStreetMap', zoom_start = 5)
markerCluster = MarkerCluster().add_to(m)

# loop through each location to mark map
for i,row in data_loc.iterrows():
    lat = data_loc.at[i, 'lat']
    lng = data_loc.at[i, 'lng']
    bird = data_loc.at[i, 'Bird']

    status = bird_status[bird_status['Bird'] == bird]

    popup = str(data_loc.at[i, 'Time']) + '<br>' + '<font size="+1"><b>' + bird + '</font></b>' + '<br>' + '<b>' + str(data_loc.at[i, 'Site']) + ', ' + str(data_loc.at[i, 'County']) + '</b>' + '<br>' + str(data_loc.at[i, 'Info'])

    # define marker colour according to scarcity
    if 'Scarce Visitor' in status['Status'].to_string(index=False):
        color = 'orange'
    elif 'Accidental' in status['Status'].to_string(index=False):
        color = 'red'
    else:
        color = 'green'

    folium.Marker(location=[lat,lng], popup = popup, icon = folium.Icon(color=color)).add_to(markerCluster)

m.save('index.html')