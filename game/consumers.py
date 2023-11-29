# chat/consumers.py
import json

from channels.generic.websocket import AsyncWebsocketConsumer
from checkers.game import Game
import random

class CheckersWrapper:
    instances = {}

    @classmethod
    def get_instance(cls, room_group_name):
        if room_group_name not in cls.instances:
            print("Creating a new game")
            cls.instances[room_group_name] = cls()
        else:
            print("Joining a game")
        return cls.instances[room_group_name]

    @classmethod
    def remove_instance(cls, room_group_name):
        if room_group_name in cls.instances:
            del cls.instances[room_group_name]

    """
    Class to handle piece validation. Current goal is to make it function as a 
    "server".

    Each player should have a startup sequence. This sequence should include:
        Player lays out their board, and the pieces that go on their board. 
        Player plugs in the Raspberry Pi and positions it over their board. 
        The Raspberry Pi loads up the python script on startup and spins in a 
            loop until it sees that all the pieces are in the starting location.
            It shows visual indicators on the sense hat until this is done.
        
    The Raspberry Pis need to connect to a server. Or, the game can be run in 
        single player. Whoever connects to the server first becomes player1, and the other as player2.
    
    Then the game "starts". 
        Each Raspberry Pi polls the "server" for whether or not it is their turn to play.
        They keep track of the server state. If they note that the player moved has switched from 
        the other player's turn to their turn, we need to update the current player's board. 
            The player's pieces may have been taken, so we need to spin in a loop until
            the player removes the pieces that were taken from them. 
        
        Otherwise, once we are sure the player's board is updated, we need to 
            look for if a player has made a move, then update the "server" game state. 

        
    """
    def __init__(self):
        self.game = Game()
        self.instance_count = 0
    
    """ return who's turn it is. """
    def whose_turn(self):
        return self.game.whose_turn()

    """ return the possible move for the current player's turn. """
    def moves(self):
        return self.game.get_possible_moves()


    """ 
    make a move
    ---
    parameters
        move
            [starting_position, ending_position]
    """
    def make_move(self, move):
        try:
            
            self.game.move(move)
        except:
            return False
        return True
    

    """
    Simulate a very very very bad AI that just makes a random move out of the 
    moveset that is available.
    """
    def random_player_move(self):
        whose_turn = self.whose_turn()

        while self.whose_turn() == whose_turn:
            moves = self.moves()

            if len(moves) == 0:
                return False

            move = moves[int(random.random() * len(moves))]

            result = self.make_move(move)
            if not result:
                return False
            #assert(result == True)
        return True
    
    """
    Converts a grid position to checkersboard notation
    """
    def grid_to_checkers(self, row, col, player):
        res = (row * 4) + 1

        if (row % 2) == 0:
            col -= 1
        
        pos = res + col//2 

        #NOTE: if player is 1, the position needs to be "mirrored"
        if (player == 1):
            return abs(pos-33)
        return pos

    """
    Converts a checkersboard notation into grid position
    """
    def checkers_to_grid(self, num, player):
            #NOTE: player 1's opponent pieces need to be "reversed"
            if (player == 1):
                num = abs(num-33)
            
            row = (num-1) // 4

            col = num - ((row * 4) + 1)
            col *= 2

            if (row % 2 == 0):
                col += 1
            
            return row, col

    """
    Input boards from the piece detection script to make a move. 
    ---

    Parameters:
        prev_board
            8x8 matrix of previous board
            REQUIRES: pieces are in valid locations on the board (all r+c are odd)
        curr_board
            8x8 matrix of current board. 
            Want to check if there were any changes by comparing it to the previous board. 
            REQUIRES: pieces are in valid locations on the board (all r+c are odd)
            REQUIRES: only one move was made between curr_board and prev_board
        player
            the side the player is playing on. Reverse the move order if '1'
            this is because both players will be playing on the same side on their boards. 
        error_location
            integer list

    Return:
        False - it's still the player's turn
        True - It's the other player's turn
    """
    def make_move_from_board(self, prev_board, curr_board, player, error_location):
        curr_player = self.whose_turn()

        # return a tuple of the move that was made. 
        def boards_same(prev_board, curr_board):
            start_pos = None
            end_pos = None

            for r in range(len(prev_board)):
                for c in range(len(prev_board[0])):
                    if prev_board[r][c] and not curr_board[r][c]:
                        start_pos = (r, c)
                    elif not prev_board[r][c] and curr_board[r][c]:
                        end_pos = (r, c)
            return start_pos, end_pos
        
        start_pos, end_pos = boards_same(prev_board, curr_board)

        if (start_pos == None) or (end_pos == None):

            # if only one of start_pos or end_pos is None, this indicates 
            # a piece might have been added or removed illegally (cheating)
            return False
        
        
        # if the move is usable, return
        if (self.make_move([self.grid_to_checkers(start_pos[0], start_pos[1], player), 
                            self.grid_to_checkers(end_pos[0],   end_pos[1],   player)])):
            return True
            
            #return curr_player == self.whose_turn()

        # the move was not possible...
        # note that the position on the board that the piece went to is not valid?
        error_location.append(end_pos)
        return False


    """
    Add opponent pieces to the board, typically would be done after opponent has moved.

    Also needs to validate that the player's board has pieces that correspond 
    to the actual game state. 
        Can occur if they are cheating (adding pieces to the board)
        Can occur if their pieces were caputured on the enemy's turn
        should highlight these squares to note this. 
    """
    def add_opponent_pieces(self, player):
        opponent_board = [[False] * 8 for _ in range(8)]

        for piece in self.game.board.pieces:
            if piece.other_player == player and not piece.captured:
                row, col = self.checkers_to_grid(piece.position, player)

                opponent_board[row][col] = True
        
        return opponent_board


    def validate_player_board(self, board, player):
        invalid_positions = []
        
        seen = set()
        for piece in self.game.board.pieces:
            if piece.player == player and not piece.captured:
                row, col = self.checkers_to_grid(piece.position, player)
                
                seen.add((row, col))
                if not board[row][col]:
                    invalid_positions.append((row, col))
        for r in range(8):
            for c in range(8):
                if ((r, c) not in seen) and (board[r][c]):
                    invalid_positions.append((r, c))
        
        return invalid_positions
    

    def is_over(self):
        if self.game.is_over():
            return self.game.get_winner()
        return 0


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"chat_{self.room_name}"

        # Join room group
        # await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        self.game = CheckersWrapper.get_instance(self.room_group_name)
        self.game.instance_count += 1

        if self.game.instance_count == 1 or self.game.instance_count == 2:
            self.player_num = self.game.instance_count
        else:
            self.player_num = -1

        await self.accept()


    async def disconnect(self, close_code):
        # Leave room group
        # await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

        # Remove the Game instance when the last user disconnects
        self.game.instance_count -= 1

        if self.game.instance_count <= 0:
            print("removing game instance. ")
            CheckersWrapper.remove_instance(self.room_group_name)

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)

        #message = text_data_json["message"]

        # TODO: validation? could be nice (this program has extreme security vulnerabilities)
        # TODO: the style sucks? yes it does. 
        
        cmd = text_data_json["command"]
        args = text_data_json["arguments"]
        results = []

        if cmd == "add_opponent_pieces":
            results.append(self.game.add_opponent_pieces(self.player_num))

        elif cmd == "validate_player_board":
            results.append(self.game.validate_player_board(args[0], self.player_num))

        elif cmd == "whose_turn":
            results.append(self.game.whose_turn())

        elif cmd == "make_move_from_board":
            error_location = []
            results.append(self.game.make_move_from_board(args[0], args[1], self.player_num, error_location))
            results.append(error_location)

        elif cmd == "random_player_move":
            results.append(self.game.random_player_move())

        elif cmd == "is_over":
            results.append(self.game.is_over())

        elif cmd == "player_num":
            results.append(self.player_num)

        ## For testing
        elif cmd == "make_move":
            results.append(self.game.make_move(args[0]))

        ## For testing
        elif cmd == "moves":
            results.append(self.game.moves())

        ## Troubleshooting
        elif cmd == "echo":
            results.append(f"echoing: {args[0]}")
        

        ## send the result back
        await self.send(
            text_data=json.dumps(
                {"type": "chat.message", 
                 "message": results})
        )

        # Send message to room group
        # await self.channel_layer.group_send(
        #     self.room_group_name, {"type": "chat.message", "message": str(msg)}
        # )

    # # Receive message from room group
    # async def chat_message(self, event):
    #     message = event["message"]

    #     # Send message to WebSocket
    #     await self.send(text_data=json.dumps({"message": message}))