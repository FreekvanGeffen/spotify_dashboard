""" Streamlit app for Spotify Playlist Report."""

import os
from datetime import datetime, timedelta

import altair as alt
import streamlit as st
from streamlit_gsheets import GSheetsConnection
from utils import convert_to_timedelta, display_image, fetch_spotify_data, parse_date
from vote import (
    add_track_to_playlist,
    check_track_in_playlist,
    create_spotipy_oauth_client,
    refresh_votes,
    search_track,
    veto_for_track,
    vote_for_track,
)

playlist_id = "36ElcXTgduenOvy2glOReJ"
data = fetch_spotify_data(
    "https://github.com/FreekvanGeffen/spotify_pull",
    "spotify_data",
    ["data_folder/playlist.ndjson", "data_folder/tracks.ndjson"],
)
df_tracks = data["data_folder/tracks.ndjson"]
df_tracks["image"] = df_tracks["image"].apply(display_image)
df_tracks["duration_timedelta"] = df_tracks["duration"].apply(convert_to_timedelta)
df_tracks["release_date"] = df_tracks["release_date"].apply(parse_date)
df_tracks["release_year"] = df_tracks["release_date"].dt.year
df_playlist = data["data_folder/playlist.ndjson"]

conn = st.connection("gsheets", type=GSheetsConnection)

latest_playlist_info = df_playlist.sort_values("date", ascending=False).iloc[0]
total_duration = df_tracks["duration_timedelta"].sum()
seven_days_ago = datetime.now() - timedelta(days=7)


if "cache_path" not in st.session_state:
    st.session_state["cache_path"] = ".cache"
    if os.path.exists(st.session_state["cache_path"]):
        os.remove(st.session_state["cache_path"])

st.balloons()

## Header
st.markdown(f"# {latest_playlist_info['name']}")
st.write(f"{latest_playlist_info['description']}")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Number of followers", latest_playlist_info["followers"])
with col2:
    st.metric("Number of tracks", latest_playlist_info["numbers"])
with col3:
    st.metric(
        "Number of hours",
        f"{int(total_duration.total_seconds() // 3600)}",
    )

## Image
html_code = f"""
<div style="text-align: center;">
    <a href="{latest_playlist_info["url"]}" target="_blank">
        <img src="{latest_playlist_info["image"]}" alt="Clickable Image" style="width: 80%;">
    </a>
</div>
<br>
"""
st.markdown(html_code, unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["Votes", "Playlist", "Tracks", "Comments"])

with tab1:
    sp = create_spotipy_oauth_client()

    if sp:
        try:
            sp.current_user()
        except Exception:
            st.error(
                "The current user is not allowed to vote, please contact FvG to get voting access."
            )
            sp = None

    if sp:
        st.success("Authorization successful!")
        df_votes = conn.read(ttl=0)

        st.write("Vote to add more tracks to this playlist!")
        if "vote_selection" not in st.session_state:
            st.session_state.vote_selection = "URL"
        st.radio(
            "Search by",
            key="vote_selection",
            options=["URL", "Track Name & Artist"],
        )
        if st.session_state.vote_selection == "URL":
            search_url = st.text_input("Spotify URL", None)
            track_name = None
            artist = None

        if st.session_state.vote_selection == "Track Name & Artist":
            track_name = st.text_input("Track Name", None)
            artist = st.text_input("Artist", None)
            search_url = None

        if search_url or (track_name and artist):
            with st.spinner("Searching..."):
                track_info = search_track(sp, search_url, track_name, artist)

            if track_info:
                with st.expander("Track Found!", expanded=True):
                    html_code = f"""
                                <div style="text-align: center;">
                                    <a href="{track_info["url"]}" target="_blank">
                                        <img src="{track_info["image"]}" alt="Clickable Image" style="width: 50%;">
                                    </a>
                                </div>
                                <br>
                                """
                    st.markdown(html_code, unsafe_allow_html=True)
                    st.write(
                        f"{track_info['name']} - {track_info['artist']} - {track_info['release_date']}"
                    )

                    # Check if track is already in playlist
                    track_check = check_track_in_playlist(
                        sp, playlist_id, track_info["url"]
                    )
                    if track_check[0]:
                        # Voting section
                        st.write("Vote for this track:")
                        vote_button = st.button("Vote")
                        if vote_button:
                            df_votes = vote_for_track(
                                sp,
                                conn,
                                df_votes,
                                track_info=track_info,
                            )
                            filtered_df = refresh_votes(conn, df_votes, seven_days_ago)
                    else:
                        st.warning(track_check[1])
            else:
                st.warning("Track not found. Please try again.")

        # Add track to playlist if enough votes
        for index, row in df_votes.iterrows():
            if row["votes"] > 4:
                df_votes.drop(index, inplace=True)
                conn.update(data=df_votes)
                st.success(add_track_to_playlist(sp, playlist_id, row["url"]))
                filtered_df = refresh_votes(conn, df_votes, seven_days_ago)

        # Show votes
        st.markdown("## Pending votes:")
        if st.button("Refresh votes"):
            filtered_df = refresh_votes(conn, df_votes, seven_days_ago)
        st.markdown(
            """<hr style="height:5px;border:none;color:#333;background-color:#333;" /> """,
            unsafe_allow_html=True,
        )

        filtered_df = refresh_votes(conn, df_votes, seven_days_ago)
        if len(filtered_df):
            for index, row in filtered_df.iterrows():
                # Create a container for each row
                with st.container():
                    col1, col2, col3, col4, col5 = st.columns(5)

                    if sp.current_user()["display_name"] not in row["voted_by"]:
                        if col1.button("Vote", key=f"action_vote_{index}"):
                            df_votes = vote_for_track(
                                sp,
                                conn,
                                df_votes,
                                url=row["url"],
                            )
                            st.rerun()
                        if col1.button("Veto", key=f"action_veto_{index}"):
                            df_votes = veto_for_track(
                                sp,
                                conn,
                                df_votes,
                                url=row["url"],
                            )
                            st.rerun()
                    col2.write(f"{row['name']} - {row['artist']}")
                    col3.write(f"[Open in Spotify]({row['url']})")
                    col4.write(f" Votes: {int(row['votes'])}")
                    col5.write(row["added_at"].strftime("%Y-%m-%d"))
                    # col7.markdown(
                    #     f'<p class="small-text">{row["voted_by"]}</p>',
                    #     unsafe_allow_html=True,
                    # )
                    st.markdown(
                        """<hr style="height:5px;border:none;color:#333;background-color:#333;" /> """,
                        unsafe_allow_html=True,
                    )


with tab2:
    ## Line Chart
    if "column_selection" not in st.session_state:
        st.session_state.column_selection = "followers"
    st.radio(
        "Select column",
        key="column_selection",
        options=["followers", "numbers"],
    )

    chart = (
        alt.Chart(df_playlist)
        .mark_line()
        .encode(
            x=alt.X("date:T", axis=alt.Axis(format="%Y-%m-%d")),
            y=f"{st.session_state.column_selection}:Q",
        )
        .properties(
            title=f"{st.session_state.column_selection} over time", width="container"
        )
    )
    st.altair_chart(chart, use_container_width=True)


with tab3:
    ## Bar chart
    if "bar_selection" not in st.session_state:
        st.session_state.bar_selection = "added_by"
    st.radio(
        "Select column",
        key="bar_selection",
        options=["added_by", "artist", "album", "release_year"],
    )
    df_plot = df_tracks[st.session_state.bar_selection].value_counts().reset_index()
    df_plot.columns = [st.session_state.bar_selection, "Count"]
    st.bar_chart(
        df_plot,
        x=st.session_state.bar_selection,
        y="Count",
    )

with tab4:
    df_comments = conn.read(worksheet="comments")

    with st.form("Add a new comment"):
        author = st.text_input("Author")
        comment = st.text_area("Comment")
        submitted = st.form_submit_button("Submit")

        if submitted and (author is not None) and (comment is not None):
            new_row = {"author": author, "comment": comment, "date": datetime.now()}
            df_comments = df_comments.append(new_row, ignore_index=True)
            conn.update(data=df_comments, worksheet="comments")

    # Display the updated DataFrame
    st.dataframe(
        data=df_comments,
        use_container_width=True,
        hide_index=True,
        column_config={
            "author": "Author",
            "comment": "Comment",
            "date": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD"),
        },
    )
