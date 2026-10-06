import requests
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup as bs
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import webbrowser
import sys

# Start a session so cookies persist
session = requests.Session()

load_dotenv()

# URLs come from .env locally, or from the repo secrets on GitHub
login_url = os.getenv("login_url")
home_url = os.getenv("home_url")
data_url = os.getenv("data_url")

missing = [name for name in ("login", "password", "login_url", "home_url", "data_url") if not os.getenv(name)]
if missing:
    sys.exit("Missing settings: " + ", ".join(missing) + " (add them to .env or the repo secrets)")

# True keeps yesterday's sightings on the map, False shows today's only.
# Set INCLUDE_YESTERDAY=false in .env (or the workflow's checkbox) to change it.
include_yesterday = (os.getenv("INCLUDE_YESTERDAY") or "true").strip().lower() == "true"

def get_login():
    return os.getenv("login")


def get_password():
    return os.getenv("password")


payload = {
    "txtEmailLogin": get_login(),
    "txtPassword": get_password(),
    "btnLogin": "Login"
}

resp = session.post(login_url, data=payload, allow_redirects=True)

# the home page's file name, e.g. the last part of home_url
home_page = home_url.rstrip("/").rsplit("/", 1)[-1]

if home_page in resp.url or "Logout" in resp.text:
    print("Logged in successfully")
else:
    print("Login failed, check login details")

response = session.get(data_url)
soup = bs(response.text, 'html.parser')

table = soup.find('table', attrs={"width": "650"})
data = []

for row in table.find_all('tr'):
   cols = row.find_all('td')
   if len(cols) == 0:
       cols = row.find_all('th')
   cols = [ele.text.strip() for ele in cols]
   data.append([ele for ele in cols if ele])  # Get rid of empty values

# create pandas dataframe of content
df_na = pd.DataFrame(data, columns=['data'])
new_df = df_na.dropna()

# split bird data rows from info rows into 2 columns
df = pd.DataFrame({'data':new_df['data'].iloc[::2].values, 'Info':new_df['data'].iloc[1::2].values})

# split bird data into separate columns
split_data = df['data'].str.split(',', expand=True).rename(columns={0:'Bird',1:'Site',2:'County'})
split_bird = split_data['Bird'].str.split('  ', expand=True).rename(columns={0:'Time',1:'Bird'})

# concat all sighting data to one dataframe
complete_data = pd.concat([split_bird['Time'],split_bird['Bird'],split_data['Site'],split_data['County'],df['Info']], sort=False, axis=1)

if include_yesterday:
    today_data = complete_data
else:
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

# ask search engines not to index the published map
m.get_root().header.add_child(folium.Element('<meta name="robots" content="noindex, nofollow">'))
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

# OUTPUT_DIR lets the GitHub Actions run save the map into the folder it publishes
output_dir = os.getenv("OUTPUT_DIR", ".")
os.makedirs(output_dir, exist_ok=True)
file_path = os.path.join(output_dir, 'index.html')
m.save(file_path)

# only open a browser when running locally; servers have no browser
if not os.getenv("CI"):
    abs_path = os.path.abspath(file_path)
    url = "file://" + abs_path

    webbrowser.open(url)
