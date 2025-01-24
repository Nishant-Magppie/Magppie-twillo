# Magppie-twillo

1. git clone <repository name>

2. cd  Magppie-twillo

3. In this first install the dependencies in this code 
   pip3 install -r requirements.txt

4. Login into your twillo and Elevenlabs 

5. Install the ngrok server for local build up: https://www.ngrok.com/ and signed up and install it in your local system.

6. Then open the ngrok.exe and then on terminal run this code ngrok http 8000 
    after that you will see a link for an example:-  "https://35cc-14-99-240-210.ngrok-free.app"       paste this link in line 127 in main.py

7. Then go to the twillo website after login 
    Go to the Twilio Console
    Navigate to Phone Numbers → Manage → Active numbers
    Select your phone number
    Under “Voice Configuration”, set the webhook for incoming calls to: https://your-ngrok-url.ngrok-free.app/outbound-call-twiml
    Set the HTTP method to POST
    a call comes section must be webhook

8. we are good to go then run command in terminal python3 main.py
