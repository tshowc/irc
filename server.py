import os
import uuid
import psycopg2
import psycopg2.extras
from flask import Flask, session
from flask.ext.socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__, static_url_path='')
app.config['SECRET_KEY'] = 'secret!'

socketio = SocketIO(app)

messages = [{'text':'test', 'name':'testName'}]
users = {}
rooms = []

def connectToDB():
  connectionString = 'dbname=ircdb2 user=postgres password=post1234 host=localhost'
  try:
    return psycopg2.connect(connectionString)
  except:
    print("Can't connect to database")

def updateRoster():
    names = []
    for user_id in  users:
        print users[user_id]['username']
        if len(users[user_id]['username'])==0:
            names.append('Anonymous')
        else:
            names.append(users[user_id]['username'])
    print 'broadcasting names'
    emit('roster', names, broadcast=True)
    
def updateRooms():
    room_list = []
    print "UPDATING ROOMS" 
    conn = connectToDB()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query = "SELECT * FROM rooms"
    cur.execute(query)

    rooms = cur.fetchall()

    for room in rooms:
         room_list.append({'room_name' : room['room_name'], 'room_id' : room['room_id']})
    emit('room', room_list, broadcast=True)
    
    
def updateMessages():
    
    conn = connectToDB()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query = "select users.username, messages.message from users JOIN junction ON users.user_id = junction.user_id JOIN rooms ON rooms.room_id = junction.room_id JOIN messages ON messages.message_id = junction.message_id WHERE rooms.room_name = %s;"
    cur.execute(query, (session['room'],))
    
    messages = cur.fetchall()
     
    for message in messages:
        message= {'name' : message['username'], 'text' : message['message']}
        emit('message', message)
        
def checkSubscribe():
    
    has_access = False
    conn = connectToDB()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query = "select subscribe.user_id from subscribe where subscribe.room_id = %s AND user_id = %s"
    cur.execute(query, (session['room_id'], session['user_id'],))
    result = cur.fetchall()
    if len(result) == 0:
        has_access = False
    else:
        has_access = True
        updateMessages()
    
    emit('is_subscribed', has_access)

        
    
@socketio.on('connect', namespace='/chat')
def test_connect():
    session['uuid']=uuid.uuid1()
    session['username']='starter name'
    print 'connected'
    print session['uuid']
    print session['username']
    
    users[session['uuid']]={'username':'New User'}
    updateRoster()
    
#    conn = connectToDB()
#    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
#    query = "SELECT * FROM messages"
#    cur.execute(query)
    
#    messages = cur.fetchall()
    
#    for message in messages:
#        message= {'name' : message['username'], 'text' : message['message']}
#        emit('message', message)

@socketio.on('message', namespace='/chat')
def new_message(message):
    #tmp = {'text':message, 'name':'testName'}
    tmp = {'text':message, 'name':users[session['uuid']]['username']}
    conn = connectToDB()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query = "INSERT INTO messages VALUES(DEFAULT, %s)"
    cur.execute(query, (message,))
    cur.close()
    conn.commit()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query2 = "INSERT INTO junction VALUES((SELECT message_id FROM messages where message = %s), (SELECT user_id FROM users where username = %s), %s)"
    cur.execute(query2, (message, session['username'], session['room_id'],))
    cur.close()
    conn.commit()
    print message
    messages.append(tmp)
    emit('message', tmp, broadcast=True)
    
@socketio.on('search', namespace='/chat')
def new_results(search):
    print "SEARCHING " + search
    #tmp = {'text':message, 'name':'testName'}
    conn = connectToDB()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query = "select users.username, messages.message from users JOIN junction ON users.user_id = junction.user_id JOIN rooms ON rooms.room_id = junction.room_id JOIN messages ON messages.message_id = junction.message_id WHERE rooms.room_name = %s AND messages.message like %s"
    cur.execute(query, (session['room'], "%" + search + "%",))
    
    results = cur.fetchall()
    
    for result in results:
        result = {'username' : result['username'], 'message' : result['message']}
        emit('search', result)
        
@socketio.on('newroom', namespace='/chat')
def create_room(roomname):
#    INSERT NEW ROOM INTO DATABASE
     print "CREATING NEW ROOM CALLED: " + roomname
     conn = connectToDB()
     cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
     query = "INSERT INTO rooms VALUES(DEFAULT, %s)"
     cur.execute(query, (roomname,))
     cur.close()
     conn.commit()
     updateRooms()
        
    
@socketio.on('change', namespace='/chat')
def change_room(rm):
    session['room'] = rm
    print 'CHANGING ROOM: ' + session['room']
    conn = connectToDB()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query = "SELECT room_id FROM rooms WHERE room_name = %s"
    cur.execute(query, (rm,))
    
    change = cur.fetchone();
    
    session['room_id'] = change['room_id']
    
    print session['room_id']
    
    checkSubscribe()
    
@socketio.on('subscribed', namespace='/chat')
def subscribe(sub):
    if sub:
        conn = connectToDB()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        query = "INSERT INTO subscribe VALUES(%s, %s)"
        cur.execute(query, (session['user_id'], session['room_id'],))
        cur.close()
        conn.commit()
        print "SUBSCRIBED TO ROOM ID: "
        print session['room_id']
        checkSubscribe()
    else: 
        print "NOT SUBSCRIBED"
        
@socketio.on('identify', namespace='/chat')
def on_identify(message):
    print 'identify' + message
    users[session['uuid']]={'username':message}
    updateRoster()

@socketio.on('login', namespace='/chat')
def on_login(updict):
    print 'login ' + updict['usn'] + updict['pw']
    usn = updict['usn']
    session['username'] = usn
    print session['username']
    pw = updict['pw']
    session['room'] = 'General'; #Room start
    session['room_id'] = 1;
    conn = connectToDB()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query = "SELECT username FROM users WHERE username = %s"
    cur.execute(query, (usn,))
    results = cur.fetchall()
    if len(results) != 0:
        query = "SELECT username, password, user_id FROM users WHERE username = %s AND password = %s"
        cur.execute(query, (usn, pw,))
        results = cur.fetchall()
        if len(results) == 0:
            print "Wrong password"
            Logged = False
            print Logged
            emit('processLogin', Logged)
        else:
            print "Logged in"
            Logged = True
            session['user_id'] = results[0]['user_id'] #grabs user_id
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = "INSERT INTO subscribe VALUES(%s, 1)"
            cur.execute(query, (session['user_id'],))
            cur.close()
            conn.commit()
            print Logged
            emit('processLogin', Logged)
    else:
        query = "INSERT INTO users VALUES(DEFAULT, %s, %s)"
        cur.execute(query, (usn, pw,))
        cur.close()
        conn.commit()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        query = "SELECT user_id FROM users WHERE username = %s"
        cur.execute(query, (usn,))
        new_user = cur.fetchone()
        Logged = True
        session['user_id'] = new_user['user_id'] #grabs user_id
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        query = "INSERT INTO subscribe VALUES(%s, 1)"
        cur.execute(query, (session['user_id'],))
        cur.close()
        conn.commit()
        print Logged
        emit('processLogin', Logged)
    #users[session['uuid']]={'username':message}
    updateRoster()
    updateRooms()
    updateMessages()


    
@socketio.on('disconnect', namespace='/chat')
def on_disconnect():
    print 'disconnect'
    if session['uuid'] in users:
        del users[session['uuid']]
        updateRoster()

@app.route('/')
def hello_world():
    print 'in hello world'
    return app.send_static_file('index.html')
    return 'Hello World!'

@app.route('/js/<path:path>')
def static_proxy_js(path):
    # send_static_file will guess the correct MIME type
    return app.send_static_file(os.path.join('js', path))
    
@app.route('/css/<path:path>')
def static_proxy_css(path):
    # send_static_file will guess the correct MIME type
    return app.send_static_file(os.path.join('css', path))
    
@app.route('/img/<path:path>')
def static_proxy_img(path):
    # send_static_file will guess the correct MIME type
    return app.send_static_file(os.path.join('img', path))
    
if __name__ == '__main__':
    print "A"

    socketio.run(app, host=os.getenv('IP', '0.0.0.0'), port=int(os.getenv('PORT', 8080)))
     
