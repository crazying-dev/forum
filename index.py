import flask
app = flask.Flask(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return "网站已迁移,新网址为<a href=\"https://www.yjlt.top\"></a>"

if __name__ == '__main__':
    app.run()