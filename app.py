from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit
import random
import string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key!' # IMPORTANT: Change this to a strong, random key in production!
socketio = SocketIO(app)

# Dictionary to store active rooms and their game data
# Each room will contain:
# 'members': list of SIDs in the room
# 'boards': dictionary mapping SID to player's board (list of 25 numbers)
# 'called_numbers': set of numbers that have been called
# 'current_turn_sid': SID of the player whose turn it is
# 'host_sid': SID of the player who created the room
# 'marked_boards': dictionary mapping SID to player's marked board (5x5 2D boolean array)
# 'bingo_progress': dictionary mapping SID to number of completed lines for each player
# 'bingo_string': dictionary mapping SID to the 'B', 'BI', 'BIN', 'BING', 'BINGO' string progress
# 'player_names': dictionary mapping SID to player's chosen name
# 'play_again_requests': dictionary mapping SID to boolean (True if requested)
# 'play_again_responses': dictionary mapping SID to 'accepted'/'rejected' (for pending requests)
rooms = {}

def generate_room_id(length=8):
    """Generates a unique random alphanumeric room ID."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_bingo_string(completed_lines):
    """Converts the number of completed lines into a BINGO string."""
    bingo_letters = "BINGO"
    return bingo_letters[:completed_lines]

@app.route('/')
def index():
    """Renders the main HTML page for the game."""
    return render_template('index.html')

@socketio.on('create_room')
def handle_create_room(data):
    """Handles a client's request to create a new game room."""
    player_name = data.get('player_name', 'Player 1')
    room_id = generate_room_id()
    rooms[room_id] = {
        'members': [request.sid],
        'boards': {},
        'called_numbers': set(),
        'current_turn_sid': None,
        'host_sid': request.sid,
        'marked_boards': {},
        'bingo_progress': {request.sid: 0},
        'bingo_string': {request.sid: ""},
        'player_names': {request.sid: player_name},
        'play_again_requests': {}, # Initialize play again requests
        'play_again_responses': {} # Initialize play again responses
    }
    join_room(room_id)
    emit('room_created', {'room_id': room_id}, to=request.sid)
    print(f"Room created: {room_id} by {request.sid} ({player_name})")

@socketio.on('join_room')
def handle_join_room(data):
    """Handles a client's request to join an existing game room."""
    room_id = data.get('room_id')
    player_name = data.get('player_name', 'Player 2')
    if room_id in rooms:
        if len(rooms[room_id]['members']) < 2:
            join_room(room_id)
            joiner_sid = request.sid
            rooms[room_id]['members'].append(joiner_sid)
            rooms[room_id]['bingo_progress'][joiner_sid] = 0
            rooms[room_id]['bingo_string'][joiner_sid] = ""
            rooms[room_id]['player_names'][joiner_sid] = player_name
            emit('room_joined', {'room_id': room_id}, to=request.sid)

            # Notify the host that a user has joined, including the new player's name
            # This is now the only notification on join, boards_received will be sent later
            emit('user_joined', {
                'sid': joiner_sid,
                'player_name': player_name
            }, to=room_id, skip_sid=joiner_sid) # Send to host only
            print(f"Player {joiner_sid} ({player_name}) joined room: {room_id}")

        else:
            emit('room_full', {'room_id': room_id}, to=request.sid)
    else:
        emit('invalid_room', {'room_id': room_id}, to=request.sid)

@socketio.on('board_submitted')
def handle_board_submitted(data):
    """Handles a player submitting their Bingo board."""
    room_id = None
    for r_id, room_data in rooms.items():
        if request.sid in room_data['members']:
            room_id = r_id
            break
    if room_id:
        rooms[room_id]['boards'][request.sid] = data['board']
        rooms[room_id]['marked_boards'][request.sid] = [[False]*5 for _ in range(5)]
        print(f"Board submitted by {request.sid} in room {room_id}: {data['board']}")

        # Only emit boards_received when BOTH players have submitted their boards
        if len(rooms[room_id]['members']) == 2 and len(rooms[room_id]['boards']) == 2:
            boards_data = {sid: rooms[room_id]['boards'][sid] for sid in rooms[room_id]['members']}
            emit('boards_received', {'boards': boards_data}, to=room_id)

@socketio.on('start_game_button_clicked')
def handle_start_game_button_clicked():
    """Handles the host clicking the 'Start Game' button."""
    room_id = None
    for r_id, room_data in rooms.items():
        if request.sid == room_data.get('host_sid'):
            room_id = r_id
            break
    if room_id and len(rooms[room_id]['members']) == 2 and len(rooms[room_id]['boards']) == 2:
        rooms[room_id]['current_turn_sid'] = random.choice(rooms[room_id]['members'])
        print(f"Game started in room {room_id}. {rooms[room_id]['current_turn_sid']} has first turn.")
        emit('game_start_signal', {
            'current_turn': rooms[room_id]['current_turn_sid'],
            'player_names': rooms[room_id]['player_names']
        }, to=room_id)
    else:
        print(f"Attempt to start game failed for {request.sid} in room {room_id}.")

@socketio.on('call_number_from_board')
def handle_call_number_from_board(data):
    """Handles a player calling a number from their board."""
    room_id = None
    for r_id, room_data in rooms.items():
        if request.sid in room_data['members']:
            room_id = r_id
            break

    if room_id:
        room_data = rooms[room_id]
        number_to_call = data['number']

        if request.sid != room_data['current_turn_sid']:
            emit('message', {'text': "It's not your turn!"}, to=request.sid)
            print(f"Player {request.sid} tried to call number out of turn in room {room_id}")
            return

        if number_to_call in room_data['called_numbers']:
            emit('message', {'text': f"Number {number_to_call} has already been called."}, to=request.sid)
            print(f"Player {request.sid} tried to call already called number {number_to_call} in room {room_id}")
            return

        room_data['called_numbers'].add(number_to_call)
        print(f"Player {request.sid} called number {number_to_call} in room {room_id}")

        for member_sid in room_data['members']:
            board_values = room_data['boards'][member_sid]
            marked_board = room_data['marked_boards'][member_sid]
            for i in range(5):
                for j in range(5):
                    if board_values[i*5 + j] == number_to_call:
                        marked_board[i][j] = True
                        break

        winners = check_bingo(room_data)

        next_turn_sid = [sid for sid in room_data['members'] if sid != request.sid][0]
        room_data['current_turn_sid'] = next_turn_sid

        emit('number_called', {
            'number': number_to_call,
            'next_turn': next_turn_sid,
            'called_numbers': list(room_data['called_numbers']),
            'bingo_progress' : {
                sid: room_data['bingo_progress'][sid] for sid in room_data['members']
            },
            'bingo_string': {
                sid: room_data['bingo_string'][sid] for sid in room_data['members']
            },
            'player_names': room_data['player_names']
        }, to=room_id)

        if winners:
            final_boards_data = {sid: room_data['boards'][sid] for sid in room_data['members']}
            final_marked_boards_data = {sid: room_data['marked_boards'][sid] for sid in room_data['members']}
            final_bingo_progress = {sid: room_data['bingo_progress'][sid] for sid in room_data['members']}
            final_bingo_string = {sid: room_data['bingo_string'][sid] for sid in room_data['members']}

            if len(winners) == 1:
                winner_sid = winners[0]
                emit('bingo_win', {
                    'winner_sid': winner_sid,
                    'final_boards': final_boards_data,
                    'final_marked_boards': final_marked_boards_data,
                    'bingo_progress': final_bingo_progress,
                    'bingo_string': final_bingo_string,
                    'called_numbers_final': list(room_data['called_numbers']),
                    'player_names': room_data['player_names']
                }, to=room_id)
                print(f"BINGO! Player {winner_sid} won in room {room_id}.")
                # Do NOT delete room here, allow for play again
            elif len(winners) == 2:
                winner_sid = request.sid # Current player is declared winner in simultaneous bingo
                emit('bingo_win', {
                    'winner_sid': winner_sid,
                    'final_boards': final_boards_data,
                    'final_marked_boards': final_marked_boards_data,
                    'bingo_progress': final_bingo_progress,
                    'bingo_string': final_bingo_string,
                    'called_numbers_final': list(room_data['called_numbers']),
                    'player_names': room_data['player_names']
                }, to=room_id)
                print(f"BINGO! Both players won simultaneously in room {room_id}. Current player {winner_sid} is declared winner.")
                # Do NOT delete room here, allow for play again

    else:
        print(f"Call number from board failed: Room not found for {request.sid}")

def check_bingo(room_data):
    """
    Checks all players' boards for Bingo lines, updates their progress,
    and determines the 'B-I-N-G-O' string.
    """
    winning_sids = []
    for player_sid in room_data['members']:
        marked_board = room_data['marked_boards'][player_sid]
        completed_lines = 0

        # Check rows
        for row in marked_board:
            if all(row):
                completed_lines += 1
        # Check columns
        for col_idx in range(5):
            if all(marked_board[row_idx][col_idx] for row_idx in range(5)):
                completed_lines += 1
        # Check diagonals
        if all(marked_board[i][i] for i in range(5)):
            completed_lines += 1
        if all(marked_board[i][4-i] for i in range(5)):
            completed_lines += 1

        room_data['bingo_progress'][player_sid] = completed_lines

        bingo_string = ""
        if completed_lines >= 1:
            bingo_string = "B"
        if completed_lines >= 2:
            bingo_string = "BI"
        if completed_lines >= 3:
            bingo_string = "BIN"
        if completed_lines >= 4:
            bingo_string = "BING"
        if completed_lines >= 5:
            bingo_string = "BINGO"
        room_data['bingo_string'][player_sid] = bingo_string

        if completed_lines >= 5:
            winning_sids.append(player_sid)
    return winning_sids

@socketio.on('request_play_again')
def handle_request_play_again():
    """Handles a player requesting to play again."""
    room_id = None
    for r_id, room_data in rooms.items():
        if request.sid in room_data['members']:
            room_id = r_id
            break

    if room_id:
        room_data = rooms[room_id]
        room_data['play_again_requests'][request.sid] = True
        requester_name = room_data['player_names'].get(request.sid, 'Player')
        print(f"Player {request.sid} ({requester_name}) requested to play again in room {room_id}.")

        other_player_sid = [sid for sid in room_data['members'] if sid != request.sid]

        if other_player_sid:
            other_player_sid = other_player_sid[0]
            # Check if the other player has also requested
            if room_data['play_again_requests'].get(other_player_sid):
                # Both requested simultaneously, auto-accept
                print(f"Both players requested to play again in room {room_id}. Auto-accepting.")
                reset_game_state(room_id)
                emit('game_reset_for_play_again', {'room_id': room_id, 'player_names': room_data['player_names']}, to=room_id)
            else:
                # Notify the other player of the request
                emit('play_again_requested', {
                    'requester_sid': request.sid,
                    'requester_name': requester_name
                }, to=other_player_sid)
        else:
            # Should not happen in a 2-player game, but handle for robustness
            print(f"No other player in room {room_id} for play again request.")

@socketio.on('respond_play_again')
def handle_respond_play_again(data):
    """Handles a player responding to a 'Play Again' request."""
    room_id = None
    for r_id, room_data in rooms.items():
        if request.sid in room_data['members']:
            room_id = r_id
            break

    if room_id:
        room_data = rooms[room_id]
        response = data.get('response') # 'accept' or 'reject'
        requester_sid = data.get('requester_sid') # The SID of the player who initiated the request

        room_data['play_again_responses'][request.sid] = response
        responder_name = room_data['player_names'].get(request.sid, 'Player')
        print(f"Player {request.sid} ({responder_name}) responded '{response}' to play again in room {room_id}.")

        other_player_sid = [sid for sid in room_data['members'] if sid != request.sid]

        if other_player_sid:
            other_player_sid = other_player_sid[0]

            if response == 'accept':
                # Check if the other player also accepted or requested
                if room_data['play_again_responses'].get(other_player_sid) == 'accept' or \
                   room_data['play_again_requests'].get(other_player_sid): # If other player already requested
                    print(f"Both players ready to play again in room {room_id}. Resetting game.")
                    reset_game_state(room_id)
                    emit('game_reset_for_play_again', {'room_id': room_id, 'player_names': room_data['player_names']}, to=room_id)
                else:
                    # Inform the requester that the other player accepted, but is waiting for their action
                    emit('play_again_response_status', {
                        'status': 'accepted_waiting',
                        'responder_name': responder_name
                    }, to=requester_sid)
            elif response == 'reject':
                # Notify the requester that their request was rejected
                emit('play_again_rejected', {
                    'rejecter_name': responder_name
                }, to=requester_sid)

                # Remove the rejecting player from the room and clean up
                leave_room(room_id)
                if request.sid in room_data['members']:
                    room_data['members'].remove(request.sid)
                if request.sid in room_data['boards']:
                    del room_data['boards'][request.sid]
                if request.sid in room_data['marked_boards']:
                    del room_data['marked_boards'][request.sid]
                if request.sid in room_data['bingo_progress']:
                    del room_data['bingo_progress'][request.sid]
                if request.sid in room_data['bingo_string']:
                    del room_data['bingo_string'][request.sid]
                if request.sid in room_data['player_names']:
                    del room_data['player_names'][request.sid]
                
                # Clear any pending play again states for the room
                room_data['play_again_requests'] = {}
                room_data['play_again_responses'] = {}

                print(f"Player {request.sid} ({responder_name}) rejected play again and left room {room_id}.")

                if not room_data['members']:
                    print(f"Room {room_id} is empty after rejection, deleting.")
                    del rooms[room_id]
                else:
                    # If one player rejects, the other player wins by default (similar to disconnect)
                    remaining_sid = room_data['members'][0]
                    remaining_player_name = room_data['player_names'].get(remaining_sid, 'You')
                    emit('game_over', {
                        'message': f'Opponent ({responder_name}) rejected play again and left the room. Game ended.',
                        'winner_sid': remaining_sid,
                        'final_boards': {}, # No final boards to show as game is not played
                        'final_marked_boards': {},
                        'bingo_progress': {},
                        'bingo_string': {},
                        'called_numbers_final': [],
                        'player_names': room_data['player_names']
                    }, to=remaining_sid)
        else:
            print(f"No other player to respond to in room {room_id}.")
    else:
        print(f"Respond play again failed: Room not found for {request.sid}")


def reset_game_state(room_id):
    """Resets the game state for a given room, keeping members and names."""
    if room_id in rooms:
        room_data = rooms[room_id]
        room_data['boards'] = {}
        room_data['called_numbers'] = set()
        room_data['current_turn_sid'] = None
        room_data['marked_boards'] = {}
        for sid in room_data['members']:
            room_data['bingo_progress'][sid] = 0
            room_data['bingo_string'][sid] = ""
        room_data['play_again_requests'] = {} # Clear requests
        room_data['play_again_responses'] = {} # Clear responses
        print(f"Game state reset for room {room_id}.")


@socketio.on('disconnect')
def handle_disconnect():
    """Handles a client disconnecting from the server."""
    for room_id, room_data in list(rooms.items()):
        if request.sid in room_data['members']:
            player_name = room_data['player_names'].get(request.sid, 'Opponent')
            room_data['members'].remove(request.sid)
            print(f"Player {request.sid} ({player_name}) disconnected from room {room_id}.")

            # Clean up player-specific data
            if request.sid in room_data['boards']:
                del room_data['boards'][request.sid]
            if request.sid in room_data['marked_boards']:
                del room_data['marked_boards'][request.sid]
            if request.sid in room_data['bingo_progress']:
                del room_data['bingo_progress'][request.sid]
            if request.sid in room_data['bingo_string']:
                del room_data['bingo_string'][request.sid]
            if request.sid in room_data['player_names']:
                del room_data['player_names'][request.sid]
            if request.sid in room_data['play_again_requests']: # Clean up play again requests
                del room_data['play_again_requests'][request.sid]
            if request.sid in room_data['play_again_responses']: # Clean up play again responses
                del room_data['play_again_responses'][request.sid]


            if not room_data['members']:
                print(f"Room {room_id} is empty, deleting.")
                del rooms[room_id]
            else:
                remaining_sid = room_data['members'][0]
                remaining_player_name = room_data['player_names'].get(remaining_sid, 'You')
                print(f"Player {remaining_sid} ({remaining_player_name}) remains in room {room_id}. Notifying game over.")

                # Prepare final board states and marked boards for the remaining player
                final_boards_data = {sid: room_data['boards'].get(sid, []) for sid in room_data['members']}
                final_marked_boards_data = {sid: room_data['marked_boards'].get(sid, [[False]*5 for _ in range(5)]) for sid in room_data['members']}
                final_bingo_progress = {sid: room_data['bingo_progress'].get(sid, 0) for sid in room_data['members']}
                final_bingo_string = {sid: room_data['bingo_string'].get(sid, "") for sid in room_data['members']}

                # Clear any pending play again states for the room
                room_data['play_again_requests'] = {}
                room_data['play_again_responses'] = {}

                emit('game_over', {
                    'message': f'Opponent ({player_name}) disconnected. Game ended.',
                    'winner_sid': remaining_sid,
                    'final_boards': final_boards_data,
                    'final_marked_boards': final_marked_boards_data,
                    'bingo_progress': final_bingo_progress,
                    'bingo_string': final_bingo_string,
                    'called_numbers_final': list(room_data['called_numbers']),
                    'player_names': room_data['player_names']
                }, to=remaining_sid)
                del rooms[room_id]
            break

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', debug=True)
