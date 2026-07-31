import sys
sys.path.append("./main")
from main.main import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)