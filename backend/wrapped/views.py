import requests
import datetime
import time
from collections import Counter

import google.generativeai as genai
from django.conf import settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from wrapped.models import (
    CustomUser,
    Panel,
    PanelType,
    SpotifyAuthData,
    SpotifyProfile,
    Wrapped,
)
from wrapped.serializers import UserSerializer, WrappedSerializer


# takes in token
# validates token
# gets email to match user
# creates + populates new user if no matching user
# returns existing user if matching user
def spotify_authenticate(token, refresh_token, expires_in):
    request_url = "https://api.spotify.com/v1/me"
    headers = {"Authorization": "Bearer " + token}

    response = requests.get(request_url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        user_email = data["email"]
        user_id = data["id"]
        user_display_name = data["display_name"]
        user, created = CustomUser.objects.get_or_create(email=user_email)

        if created:
            user.auth_data = SpotifyAuthData(
                access_token=token, refresh_token=refresh_token, expires_in=expires_in
            )
            user.spotify_profile = SpotifyProfile(spotify_id=user_id)

        else:
            user.auth_data.access_token = token
            user.auth_data.refresh_token = refresh_token
            user.auth_data.expires_in = expires_in

            user.spotify_profile.spotify_id = user_id
            user.spotify_profile.display_name = user_display_name

        user.auth_data.save()
        user.spotify_profile.save()

        user.save()
        return user

    return None


@api_view(["POST"])
@permission_classes([AllowAny])
def register_by_access_token(request):
    token = request.data.get("access_token")
    refresh_token = request.data.get("refresh_token")
    expires_in = request.data.get("expires_in")
    user = spotify_authenticate(token, refresh_token, expires_in)

    if user:
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "auth_token": token.key,
            },
            status=status.HTTP_200_OK,
        )
    else:
        return Response(
            {"errors": {"auth_token": "Invalid token"}},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def get_user(request):
    user = request.user
    if request.method == "GET":
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    elif request.method == "POST":
        data = request.data
        user.username = data["username"]
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]
        user.is_registered = True
        user.save()

        return Response(
            {
                "message": "User information successfully updated",
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            status=status.HTTP_200_OK,
        )

    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def authentication_test(request):
    print(request.user)
    return Response(
        {"message": "User successfully authenticated"},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response(status=status.HTTP_200_OK)


@api_view(["GET"])
def spotify_top_artists(request):
    access_token = request.user.auth_data.access_token
    headers = {"Authorization": f"Bearer {access_token}"}
    top_artists_response = requests.get(
        "https://api.spotify.com/v1/me/top/artists?limit=5", headers=headers
    )

    if top_artists_response.status_code != 200:
        return Response(
            {"error": "Failed to fetch top artists from Spotify API."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    top_artists = top_artists_response.json().get("items", [])
    artists = [
        {"name": artist["name"], "popularity": artist["popularity"]}
        for artist in top_artists
    ]

    return Response(artists, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def spotify_top_tracks(request):
    user = request.user
    token = user.auth_data.access_token
    url = "https://api.spotify.com/v1/me/top/tracks?time_range=short_term&limit=10"
    headers = {"Authorization": "Bearer " + token}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return Response(
            {"error": "Failed to fetch top tracks from Spotify API."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    body = response.json()
    return Response(body, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def spotify_top_genres(request):
    user = request.user
    token = user.auth_data.access_token
    url = "https://api.spotify.com/v1/me/top/artists?time_range=short_term&limit=20"
    headers = {"Authorization": "Bearer " + token}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return Response(
            {"error": "Failed to fetch top artists from Spotify API."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    body = response.json()
    genres = []

    # Collect genres from each artist
    for artist in body.get("items", []):
        genres.extend(artist.get("genres", []))

    # Count and sort genres
    genre_counts = Counter(genres)
    top_genres = genre_counts.most_common(10)  # Adjust the number as needed

    return Response({"top_genres": top_genres}, status=status.HTTP_200_OK)


@api_view(["GET"])
def top_tracks(request):
    access_token = request.user.auth_data.access_token

    # Get top tracks
    headers = {"Authorization": f"Bearer {access_token}"}
    top_tracks_response = requests.get(
        "https://api.spotify.com/v1/me/top/tracks?limit=5", headers=headers
    )

    if top_tracks_response.status_code != 200:
        return Response(
            {"error": "Failed to fetch top tracks from Spotify API."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    top_tracks = top_tracks_response.json().get("items", [])
    tracks = [
        {"name": track["name"], "popularity": track["popularity"]}
        for track in top_tracks
    ]

    return Response(tracks, status=status.HTTP_200_OK)


@api_view(["GET"])
def recently_played_tracks(request):
    access_token = request.user.auth_data.access_token
    headers = {"Authorization": f"Bearer {access_token}"}

    four_weeks_ago = datetime.datetime.now() - datetime.timedelta(weeks=4)
    after_timestamp = int(time.mktime(four_weeks_ago.timetuple()) * 1000)
    print(after_timestamp)

    all_tracks = []

    params = {"limit": 50, "after": after_timestamp}
    while True:
        response = requests.get(
            "https://api.spotify.com/v1/me/player/recently-played",
            headers=headers,
            params=params,
        )

        if response.status_code != 200:
            return Response(
                {"error": "Failed to fetch recently played tracks from Spotify API."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = response.json().get("items", [])
        all_tracks.extend(
            [
                {
                    "name": item["track"]["name"],
                    "played_at": item["played_at"],
                    "artists": [artist["name"] for artist in item["track"]["artists"]],
                }
                for item in data
            ]
        )

        if "cursors" in response.json() and response.json()["cursors"]:
            params["after"] = response.json()["cursors"]["after"]
            print("here")
        else:
            break

    return Response(all_tracks, status=status.HTTP_200_OK)


@api_view(["GET"])
def llm_generate(request):
    access_token = request.user.auth_data.access_token
    headers = {"Authorization": f"Bearer {access_token}"}
    genai.configure(api_key=settings.GOOGLE_CLIENT_ID)

    top_artists_response = requests.get(
        "https://api.spotify.com/v1/me/top/artists?limit=5", headers=headers
    )

    if top_artists_response.status_code != 200:
        return Response(
            {"error": "Failed to fetch top artists from Spotify API."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    top_artists = top_artists_response.json()
    genres = {genre for artist in top_artists["items"] for genre in artist["genres"]}
    artist_names = [artist["name"] for artist in top_artists["items"]]

    model = genai.GenerativeModel("gemini-1.5-flash")
    gemini_prompt = f"""
        Create a vibrant personality description for someone who:
        - Frequently listens to genres like: {', '.join(genres)}
        - Enjoys artists such as: {', '.join(artist_names)}

        Please describe the following with clear labels:

        1. Personality & Thinking Style: Describe likely personality traits and thinking style in 3-4 words.
        2. Fashion Choices: Describe probable fashion choices and aesthetic preferences in 3-4 words. 
           Make sure it's specific clothing.
        3. Behavior: Describe typical behaviors and habits in 3-4 words.

        Make sure each section starts with the label 
        (e.g., "Personality & Thinking Style:", "Fashion Choices:", "Behavior:").
        You also don't have to add the numbers, they're just there to help you structure your response.
        """
    response = model.generate_content(gemini_prompt)
    full_description = response.text.strip()

    personality_description = ""
    fashion_choices = ""
    behavior_description = ""

    if "Personality & Thinking Style:" in full_description:
        personality_description = (
            full_description.split("Personality & Thinking Style:")[1]
            .split("Fashion Choices:")[0]
            .strip()
        )

    if "Fashion Choices:" in full_description:
        fashion_choices = (
            full_description.split("Fashion Choices:")[1].split("Behavior:")[0].strip()
        )

    if "Behavior:" in full_description:
        behavior_description = full_description.split("Behavior:")[1].strip()

    return Response(
        {
            "personality_description": personality_description,
            "fashion_choices": fashion_choices,
            "behavior_description": behavior_description,
            "based_on": {"genres": list(genres), "artists": artist_names},
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def danceability_score(request):
    access_token = request.user.auth_data.access_token
    headers = {"Authorization": f"Bearer {access_token}"}

    top_tracks_response = requests.get(
        "https://api.spotify.com/v1/me/top/tracks?limit=10", headers=headers
    )

    if top_tracks_response.status_code != 200:
        return Response(
            {"error": "Failed to fetch top tracks from Spotify API."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    tracks = top_tracks_response.json().get("items", [])
    track_ids = [track["id"] for track in tracks]

    audio_features_response = requests.get(
        f"https://api.spotify.com/v1/audio-features?ids={','.join(track_ids)}",
        headers=headers,
    )

    if audio_features_response.status_code != 200:
        return Response(
            {"error": "Failed to fetch audio features from Spotify API."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    audio_features = audio_features_response.json().get("audio_features", [])

    total_danceability = sum(
        feature["danceability"] for feature in audio_features if feature
    )
    average_danceability = (
        total_danceability / len(audio_features) if audio_features else 0
    )

    return Response({"average_danceability": (int)(100 * average_danceability)})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def wrapped(request):
    user = request.user
    data = request.data
    if request.method == "POST":
        if not ("name" in data and data["name"]):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        new_wrapped = generate_wrapped(user, data["name"])
        new_wrapped.save()
        serializer = WrappedSerializer(new_wrapped)
        return Response(
            {
                "message": "New wrapped successfully created",
                "wrapped": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    elif request.method == "GET":
        serializer = WrappedSerializer(Wrapped.objects.filter(user=user), many=True)
        return Response({"wrapped_list": serializer.data}, status=status.HTTP_200_OK)

    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


def generate_wrapped(user, name):
    PANEL_ORDER = [
        PanelType.INTRO,
        PanelType.TOP_TRACKS,
        PanelType.DANCE,
        PanelType.TOP_GENRES,
        PanelType.PRE_LLM,
        PanelType.LLM,
        PanelType.PRE_GAME,
        PanelType.GAME,
    ]
    new_wrapped = Wrapped()
    new_wrapped.user = user
    new_wrapped.name = name
    new_wrapped.save()

    order = 1
    for panel_type in PANEL_ORDER:
        generate_panel(user, new_wrapped, order, panel_type)
        order += 1

    return new_wrapped


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_wrapped_with_id(request, wrapped_id):
    user = request.user
    try:
        serializer = WrappedSerializer(Wrapped.objects.get(id=wrapped_id, user=user))
        return Response({"wrapped": serializer.data}, status=status.HTTP_200_OK)
    except Wrapped.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


def generate_panel(user, parent_wrapped, order, panel_type):
    panel = Panel()
    panel.wrapped = parent_wrapped
    panel.order = order
    panel.type = panel_type
    match panel_type:
        case PanelType.INTRO:
            panel.data = generate_data_intro(user)
        case PanelType.LLM:
            panel.data = generate_data_llm(user)
        case PanelType.PRE_LLM:
            panel.data = generate_data_pre_llm(user)
        case PanelType.DANCE:
            panel.data = generate_data_danceability(user)
        case PanelType.PRE_GAME:
            panel.data = generate_data_pre_game(user)
        case PanelType.TOP_GENRES:
            panel.data = generate_data_top_genres(user)
        case PanelType.TOP_TRACKS:
            panel.data = generate_data_top_tracks(user)
        case PanelType.GAME:
            panel.data = generate_data_game(user)
        case default:
            return Exception(f"Invalid panel type specified {default}")

    panel.save()
    return panel


def generate_data_intro(user):
    return {}


def generate_data_llm(user):
    return {}


def generate_data_pre_llm(user):
    return {}


def generate_data_top_tracks(user):
    return {}


def generate_data_top_genres(user):
    return {}


def generate_data_pre_game(user):
    return {}


def generate_data_danceability(user):
    return {}


def generate_data_game(user):
    return {}
