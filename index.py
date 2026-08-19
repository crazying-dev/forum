import sys
sys.path.append("./main")
from main.main import app

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=3000)