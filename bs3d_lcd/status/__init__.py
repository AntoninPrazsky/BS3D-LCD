"""The BS3D server's status display (BS3D-LCD#1).

Sources read the server from outside into one ``State``; pages draw it under
a status strip; the ``Director`` rotates them with an eased push, gives the
screen to an alarm and sounds the siren by swinging V0; a push button
acknowledges the alarm or shows the next page.
"""
