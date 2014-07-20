# coding: utf-8

import httplib2
import os
import sys
import pprint
from dateutil import parser as dateparser
from datetime import datetime, timedelta
import pytz

from apiclient.discovery import build
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow


# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the {{ Google Cloud Console }} at
# {{ https://cloud.google.com/console }}.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
CLIENT_SECRETS_FILE = "client_secrets.json"

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

   %s

with information from the {{ Cloud Console }}
{{ https://cloud.google.com/console }}

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__),
                                   CLIENT_SECRETS_FILE))

# This OAuth 2.0 access scope allows for read-only access to the authenticated
# user's account, but not other types of account access.
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
                               message=MISSING_CLIENT_SECRETS_MESSAGE,
                               scope=YOUTUBE_READONLY_SCOPE)

storage = Storage("%s-oauth2.json" % sys.argv[0])
credentials = storage.get()

if credentials is None or credentials.invalid:
    flags = argparser.parse_args()
    credentials = run_flow(flow, storage, flags)

youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                http=credentials.authorize(httplib2.Http()))

subscriptions_request = youtube.subscriptions().list(
    mine=True,
    part='snippet'
)

subscriptions = {}

print 'Requesting channels from current user...'

while subscriptions_request:
    subscriptions_response = subscriptions_request.execute()
    for subscription in subscriptions_response['items']:
        channel_id = subscription['snippet']['resourceId']['channelId']
        channel_title = subscription['snippet']['title']
        subscriptions.update({
            channel_id: {
                'title': channel_title,
                'channelId': channel_id
            }
        })
    subscriptions_request = youtube.subscriptions() \
        .list_next(subscriptions_request, subscriptions_response)

#pprint.pprint(subscriptions)
#pprint.pprint(subscriptions.keys())

channels_response = youtube.channels().list(
    part='contentDetails',
    id=','.join(subscriptions.keys())
).execute()

print 'Requesting upload playlist from channels...'

cutoff_date = datetime.utcnow()-timedelta(days=7)
cutoff_date = cutoff_date.replace(tzinfo=pytz.utc)

for channel in channels_response['items']:
    uploads_list_id = channel['contentDetails']['relatedPlaylists']['uploads']
    current_channel = subscriptions[channel['id']]
    current_channel.update({
        'uploads': uploads_list_id,
        'videos': []
    })
    print "Videos in list %s of channel %s" % (uploads_list_id, current_channel['title'])

    playlistitems_list_request = youtube.playlistItems().list(
        playlistId=uploads_list_id,
        part="snippet",
        maxResults=50
    )

    stale = False
    while playlistitems_list_request and not stale:
        playlistitems_list_response = playlistitems_list_request.execute()
        for playlist_item in playlistitems_list_response["items"]:
            snippet = playlist_item['snippet']
            published_date = dateparser.parse(snippet['publishedAt'])
            if cutoff_date > published_date:
                stale = True
                break
            title = snippet["title"]
            video_id = snippet["resourceId"]["videoId"]
            current_channel['videos'].append(video_id)
        playlistitems_list_request = youtube.playlistItems().list_next(
            playlistitems_list_request, playlistitems_list_response)

prune_keys = []
for key, subscription in subscriptions.iteritems():
    if not subscription['videos']:
        prune_keys.append(key)

for key in prune_keys:
    subscriptions.pop(key, None)

pprint.pprint(subscriptions, depth=3)

# Now we can easily make a list of all of the videos that were uploaded between
# cutoff_date and now, and insert them in a playlist. We might also need to
# also sort the videos by their published time.