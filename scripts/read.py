#!/usr/bin/env python

import time
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522

reader = SimpleMFRC522()

try:
    print("Waiting for you to scan an RFID sticker/card (Press Ctrl+C to exit)...")
    
    while True:
        # Read the card ID
        id = reader.read()[0]
        print(f"The ID for this card is: {id}")
        
        # Short pause so it doesn't spam reads if the card is held near the reader
        time.sleep(1)

except KeyboardInterrupt:
    print("\nProgram stopped by user.")

finally:
    GPIO.cleanup()
    print("GPIO cleaned up. Exiting.")