import requests
import chess
import chess.engine
import time
import joblib
import dataclass
import re

path = "C:/Users/calal/Downloads/lc0-v0.30.0-windows-gpu-nvidia-cuda/"
lc0_path = f"{path}lc0.exe"

board_evals = {}#joblib.load('board_evals.dat')
candidate_cache = {}#joblib.load('candidate_cache.dat')

def extract_v_value(string):
    match = re.search(r'\(V:\s*([-\d.]+)\)', string)
    if match:
        return float(match.group(1))
    else:
        return None
    
def get_candidate_moves(fen, threshold, speeds=["blitz", "rapid", "classical"], ratings=[0,4000]):
    """
    Queries the Lichess opening explorer for candidate moves given a FEN string.
    Returns a dictionary of moves to frequency.
    """
    if fen in candidate_cache.keys():
        return candidate_cache[fen]
    
    url = "https://explorer.lichess.ovh/lichess"
    params = {"fen": fen, 
              "speeds[]": speeds, 
              "ratings[]": ratings,
              "topGames": 0, 
              "recentGames": 0,
              "moves": 10,
            }
    time.sleep(1)
    response = requests.get(url, params=params)
    data = response.json()

    moves = {}
    for move in data['moves']:
        uci_move = move['uci']
        frequency = move['white'] + move['draws'] + move['black']
        moves[uci_move] = frequency

    total = sum(moves.values())
    moves_to_delete = []
    for move in moves.keys():
        moves[move] /= total
        if moves[move] < threshold:
            moves_to_delete.append(move)
    
    for move in moves_to_delete:
        del moves[move]
    
    candidate_cache[fen] = moves
    return moves


def evaluate_position(engine, board):
    # Use LC0 to evaluate the position
    string = engine.analyse(board, chess.engine.Limit(nodes=1))['string']
    return extract_v_value(string)

def calculate_expected_value(response_candidates, evaluation):
    ev = 0
    for response in response_candidates.keys():
        ev += response_candidates[response] * evaluation[response]
    
    return ev

def recursive_evaluation(engine, board, frequency=1, ev=0, threshold=0.1):
    fen = board.fen()
    candidates = get_candidate_moves(fen, 0.005)
    move_expected_values = {}
    move_expected_values[None] = ev

    # Evaluate each candidate move
    for move in candidates:
        board.push(chess.Move.from_uci(move))

        response_candidates = get_candidate_moves(board.fen(), 0.02)

        move_expected_values[move] = 0
        for response, response_freq in response_candidates.items():
            board.push(chess.Move.from_uci(response))
            naive_eval = evaluate_position(engine, board)
            if naive_eval + 0.5 < max(move_expected_values.values()) or frequency*response_freq < threshold:
                move_expected_values[move] += naive_eval * response_freq
            else:
                _, evaluation = recursive_evaluation(engine, board, frequency * response_freq, max(move_expected_values.values()))
                move_expected_values[move] += evaluation * response_freq
                print(fen, move, response, frequency * response_freq, evaluation)
            board.pop()

        board.pop()
    joblib.dump(board_evals, "board_evals.dat")
    joblib.dump(candidate_cache, "candidate_cache.dat")
    
    # Find the move with the maximum expected value
    best_move = max(move_expected_values, key=move_expected_values.get)
    return best_move, move_expected_values[best_move]

engine = chess.engine.SimpleEngine.popen_uci(lc0_path)
engine.configure({"VerboseMoveStats": "true"})
best_move, best_evaluation, ev = recursive_evaluation(engine, chess.Board())
engine.quit()