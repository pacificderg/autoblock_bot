#!/usr/bin/env python3
from telethon import TelegramClient, sync

api_id = input("Enter api id: ")
api_hash = input("Enter api hash: ")
client = TelegramClient('scrape_room', api_id, api_hash)
client.start()

while True:
    room_name = input("Enter room name: ")
    room = client.get_entity(room_name)

    with open("{}_members.csv".format(room_name.strip("@")), "wb") as output:
        output.write("id,username,first_name,last_name\n".encode("utf-8"))

        for i, member in enumerate(client.iter_participants(room)):
            username = member.username if member.username is not None else ""
            first_name = member.first_name if member.first_name is not None else ""
            last_name = member.last_name if member.last_name is not None else ""
            output.write("{},{},\"{}\",\"{}\"\n".format(member.id, username, first_name, last_name).encode("utf-8"))
            if i % 100 == 0:
                print(".", end="")

        print()
