![alt text](minimum_length.png)

Currently supports symbolic and english formalizations

USAGE: (client not yet integrated)

python3 server/app.py

curl -X POST http://localhost:PORT_NUMBER/formalize \
     -H "Content-Type: application/json" \
     -d '{"fileUrl":"./uploads/'YOUR_PDF.pdf'", "formatType":"logic"}'


You will need your own API key for now 😔 