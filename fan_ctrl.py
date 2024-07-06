#!/usr/bin/env python3
import subprocess
import time
import math
import socket
import requests # Must have requests installed (pip install requests)

###############
## Variables ##
###############

# Max temperature before it turns fan control over to the iDRAC
TEMPMAX=87
# Cooldown temperature target
TEMPTARGET=68
# Minimum percentage to run fans at
SPEEDMIN=8
# How often to check the temperature
INTERVAL=5
# Flag for catching failures to read temperature
READFAIL=0
# Set high temp cool down flag to off for the first loop
COOLINGDOWN = "no"
# Set fan control to auto for the first loop
FANCTRL = "auto"
# Initalize the last CPU temperature reading
LASTREADING = 0
# Get hostname
HOSTNAME = socket.gethostname()
# Set function type (l = linear, e = exponential)
FUNCTION_TYPE = "e"

## Linear Equation 
# Use linear equation (y = A + Bx) to get fan speed percentage
LIN_A = -139.4
LIN_B = 2.68

## Exponential Equation
# Use exponential equation (y = AB^X) to get fan speed percentage
# EXP_A = 0.00080092652
# EXP_B = 1.146157619
EXP_A = 0.0049
EXP_B = 1.1221

###############
## Functions ##
###############

# Set fan state to auto or manual
def set_fan_state(state):
    global FANCTRL
    if state == "manual":
        if FANCTRL != "manual":
            print ("Setting fan control to manual")
            while True:
                cmd = subprocess.run(["ipmitool", "raw", "0x30", "0x30", "0x01", "0x00"])
                if cmd.returncode == 0:
                    break
            FANCTRL = "manual"
    elif state == "auto":
        if FANCTRL != "auto":
            print ("Setting fan control to auto")
            while True:
                cmd = subprocess.run(["ipmitool", "raw", "0x30", "0x30", "0x01", "0x01"])
                if cmd.returncode == 0:
                    break
            FANCTRL = "auto"
    elif state == "first_loop":
        print("Starting fan control...")
    else:
        print ("FUNCTION ERROR: set_fan_state incorrect parameter")

# Set fan speed. If not successful, alert and set fans to auto
def set_fan_speed(speed):
    cmd = subprocess.run(["ipmitool", "raw", "0x30", "0x30", "0x02", "0xff", hex(speed)], stdout=subprocess.PIPE)
    if cmd.returncode == 0:
        # print("Temperature changed to %i - Setting fan speed to %i%%" %(HOTTESTCPU,speed))
        pass
    else:
        print ("FAILED TO SET FAN SPEED. CHANGING TO AUTO")
        set_fan_state("auto")

# Send Telegram message
def send_to_telegram(message):
    apiToken = 'GET FROM KEEPASS'
    chatID = 'GET FROM KEEPASS'
    apiURL = f'https://api.telegram.org/bot{apiToken}/sendMessage'

    try:
        response = requests.post(apiURL, json={'chat_id': chatID, 'text': message})
        print(response.text)
    except Exception as e:
        print(e)

###################
## Initial State ##
###################

# Set state for the first iteration
FANCTRL="first_loop"
set_fan_state("manual")

###############
## Execution ##
###############

# Continually check the temperature and adjust the fan speed accordingly
while True:
    # Request IPMI results
    request = subprocess.run(["ipmitool", "sdr", "type", "temperature"], stdout=subprocess.PIPE)
    if request.returncode != 0:
        if READFAIL == 0:
            print ("ERROR: FAILED TO READ TEMP SENSOR. TRYING AGAIN.")
            READFAIL = 1
            time.sleep(INTERVAL)
            continue
        else:
            print ("ERROR:CONSECUTIVE READ FAILURES! Giving control to iDRAC")
            set_fan_state("auto")
            continue
    # Store results from request
    temps_and_text = request.stdout.decode('utf-8')
    # Pull out the integers
    temps = [int(s) for s in temps_and_text.split() if s.isdigit()]
    # Sort from lowest to highest
    temps.sort()
    # Delete all temps except the highest (the hottest of the CPU cores)
    del temps[:-1]
    # Pull the temperature out of the list and store it as an integer
    HOTTESTCPU = temps[0]
    # If the temperature hasn't changed restart the loop
    if HOTTESTCPU == LASTREADING:
        time.sleep(INTERVAL)
        continue
    else:
        LASTREADING = HOTTESTCPU
    # If the CPU has cooled down to the target temperature, turn off the cooldown
    if COOLINGDOWN == "yes":
        if HOTTESTCPU <= TEMPTARGET:
            print("Cooldown temperature reached.")
            send_to_telegram("%s reached cooldown temp - %dC. \nControl given to script." %(HOSTNAME, HOTTESTCPU))
            COOLINGDOWN = "no"
            set_fan_state("manual")
    # If the CPU is hotter than the max temperature, enable cooldown
    if COOLINGDOWN == "no":
        if HOTTESTCPU >= TEMPMAX:
            print("Current temp: %d\tMax temp: %d\tCooling down to %d" %(HOTTESTCPU, TEMPMAX, TEMPTARGET))
            set_fan_state("auto")
            send_to_telegram("%s reached %dC! \nControl given to iDRAC." %(HOSTNAME, HOTTESTCPU))
            COOLINGDOWN = "yes"
            continue
        # Spool fan speed according to the hottest CPU tempearture
        #####################
        ## Linear Equation ##
        #####################
        if FUNCTION_TYPE == "l":
            TARGET_SPEED = LIN_B * HOTTESTCPU
            TARGET_SPEED = LIN_A + TARGET_SPEED
            TARGET_SPEED = math.ceil(TARGET_SPEED)
        ##########################
        ## Exponential Equation ##
        ##########################
        else:
            TARGET_SPEED = EXP_B ** HOTTESTCPU
            TARGET_SPEED = TARGET_SPEED * EXP_A
            TARGET_SPEED = math.ceil(TARGET_SPEED)

        # If equation wants to set the fan speed too low, set it to SPEEDMIN
        if TARGET_SPEED < SPEEDMIN:
            set_fan_speed(SPEEDMIN)
        # Set fan speed to the new target speed.
        else:
            set_fan_speed(TARGET_SPEED)
    else:
        print("Current temp: %d\tMax temp: %d\tCooling down to %d" %(HOTTESTCPU, TEMPMAX, TEMPTARGET))
        send_to_telegram("%s is in cooldown - %dC." %(HOSTNAME, HOTTESTCPU))
    
    # Reset the read fail flag
    READFAIL = 0

    # Pause between execution cycles
    time.sleep(INTERVAL)
