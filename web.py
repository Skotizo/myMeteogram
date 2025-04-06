from datetime import timedelta
from flask import Flask, request, render_template, jsonify, abort, session
import requests
from PIL import Image
from io import BytesIO
import logging
from itsdangerous import URLSafeTimedSerializer
import time 
import os
from flask_cors import CORS
import base64

#TODO fix timezone in graph is set statically cp6

logging.basicConfig(level=logging.DEBUG)

application = Flask(__name__)
SECRET_KEY = os.urandom(24)
application.secret_key = SECRET_KEY
application.config['SESSION_COOKIE_SECURE'] = True  # Requires HTTPS
application.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevents JavaScript access
application.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Helps prevent CSRF attacks
serializer = URLSafeTimedSerializer(SECRET_KEY)
CORS(application, origins=["https://mymeteogram.com"]) # MUST CHANGE. ADD YOURS
@application.route('/')
def home():
    csrf_token = serializer.dumps(str(time.time()))
    session['csrf_token'] = csrf_token
    return render_template('index.html', csrf_token=csrf_token)

@application.route('/about')
def about():
    csrf_token = serializer.dumps(str(time.time()))
    session['csrf_token'] = csrf_token
    return render_template('about.html', csrf_token=csrf_token)

@application.route('/terms')
def terms():
    csrf_token = serializer.dumps(str(time.time()))
    session['csrf_token'] = csrf_token
    return render_template('terms.html', csrf_token=csrf_token)

@application.route('/privacy')
def privacy():
    csrf_token = serializer.dumps(str(time.time()))
    session['csrf_token'] = csrf_token
    return render_template('privacy.html', csrf_token=csrf_token)


@application.route('/zipToGeo')
def zipToGeo():
    token = request.args.get('csrf_token')

    # Validate CSRF token
    try:
        valid_token = serializer.loads(token)
    except:
        abort(403)  # Forbidden if token is invalid

    zipCode = request.args.get('zip', type=int)
    if zipCode is None:
        return "zip arg required", 400

    if zipCode > 0:
        with open("zip.csv", "r", encoding="utf-8-sig") as zipfile:
            for line in zipfile:
                if line.startswith(f"US,{zipCode},"):
                    # Parse the line
                    parts = line.strip().split(",")

                    # Extract lat/long
                    lat = parts[7]
                    lon = parts[8]

                    city = parts[2]
                    state = parts[3]

                    # Return JSON to the frontend
                    return jsonify({
                        "lat": lat,
                        "lon": lon,
                        "city": city,
                        "state": state
                    })

        # If we reach here, ZIP wasn't found
        return "ZIP code not found", 404

    # If zipCode <= 0
    return "Invalid ZIP code", 400

@application.route('/meteogram')
def meteogram():
    token = request.args.get('csrf_token')
    try:
        valid_token = serializer.loads(token)  # 300 seconds = 5 minutes
    except:
        abort(403)  # Forbidden
    latitude = request.args.get('lat', type=float)
    longitude = request.args.get('lon', type=float)
    if latitude is None or longitude is None:
        return "Latitude and longitude are required", 400
    #TODO test is usa lat lon
    #logging.debug(f'Received lat: {latitude}, lon: {longitude}')
    wfo, zoneId, forecastUrl, city, state = getOffice(latitude, longitude)
    periods = getForecast(forecastUrl)
    #json payload.
    image = getImage(wfo, zoneId, latitude, longitude)
    if not image:
        logging.error('No image to send.')
        return "Failed to retrieve the image", 500

    # Convert the image to a Base64 string
    img_io = BytesIO()
    image.save(img_io, 'PNG')
    img_io.seek(0)
    image_base64 = base64.b64encode(img_io.read()).decode('utf-8')

    # Return JSON that contains both the forecast data and the image
    return jsonify({
        "latitude": latitude,
        "longitude": longitude,
        "city": city,
        "state": state,
        "wfo": wfo,
        "zoneId": zoneId,
        "forecastUrl": forecastUrl,
        "periods": periods,               # The entire forecast array
        "imageBase64": image_base64       # The encoded image
    })

def getForecast(forecastUrl):
    try:
        with requests.get(forecastUrl) as forecast_response:
            forecast_response.raise_for_status()
            data = forecast_response.json()
        periods = data['properties']['periods']
        #print(periods)
        return periods

    except requests.RequestException as e:
        logging.error(f"Error retrieving office data from position data: {e}")
        return None  

def getOffice(latitude, longitude): 
    points_url = f"https://api.weather.gov/points/{latitude},{longitude}"
    try:
        with requests.get(points_url) as points_response:
            points_response.raise_for_status()
            data = points_response.json()
        wfo = data['properties']['cwa']
        zoneId = data['properties']['forecastZone'].split("/")[-1]
        forecastUrl = data['properties']['forecast']
        city = data['properties']['relativeLocation']['properties']['city']
        state = data['properties']['relativeLocation']['properties']['state']
        return wfo, zoneId, forecastUrl, city, state
    except requests.RequestException as e:
        logging.error(f"Error retrieving office data from position data: {e}")
        return None    

def getImage(wfo,zoneId, latitude, longitude):
    meteogram_url = f"https://forecast.weather.gov/meteograms/Plotter.php?lat={latitude}&lon={longitude}&wfo={wfo}&zcode={zoneId}&gset=25&gdiff=5&unit=0&tinfo=CY6&ahour=0&pcmd=1111111111111111111111111111111111111111111111111111111111&lg=en&indu=1!1!1!1&dd=1&bw=&hrspan=48&pqpfhr=6&psnwhr=6"
    try:
        #logging.debug(f'Requesting meteogram from URL: {meteogram_url}')
        with requests.get(meteogram_url) as meteogram_response:
            meteogram_response.raise_for_status()
            return Image.open(BytesIO(meteogram_response.content))
    except requests.RequestException as e:
        logging.error(f"Error retrieving image for URL{meteogram_url}: {e}")
        return None

if __name__ == '__main__':
    application.run(debug=False)
