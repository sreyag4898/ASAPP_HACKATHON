from flask import Flask, request, jsonify, render_template, session
from datetime import datetime
import random, string
from rapidfuzz import process

app = Flask(__name__)
app.secret_key = 'secret'

# Example list of valid cities
VALID_CITIES = [
    "Delhi", "Mumbai", "Bengaluru", "Chennai", "Hyderabad", "Kolkata", "Pune", "Jaipur",
    "Ahmedabad", "Goa", "Cochin", "Lucknow", "Patna", "Chandigarh", "Bhopal"
]

flights = {}

# Simple airline policy knowledge base
POLICY_KB = {
    "baggage": "Each passenger is allowed one carry-on bag up to 7 kg and one checked bag up to 15 kg.",
    "refund": "Refunds are processed within 5–7 business days after cancellation.",
    "cancel": "Flights can be cancelled up to 24 hours before departure without penalty.",
    "change": "Flight date and time changes can be made up to 12 hours before departure, subject to availability.",
    "checkin": "Online check-in opens 24 hours before departure and closes 2 hours before domestic flights.",
    "meal": "Meals are complimentary on flights longer than 90 minutes. Snacks and beverages are available for purchase on shorter flights.",
}


def generate_booking_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def validate_city(input_city):
    """Return best match for city if similarity is above threshold."""
    best_match, score, _ = process.extractOne(input_city, VALID_CITIES)
    return best_match if score > 80 else None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/chat', methods=['POST'])
def chat():
    msg = request.json.get("message", "").strip()
    lower_msg = msg.lower()
    response = ""

    if 'booking_stage' not in session:
        session['booking_stage'] = None
        session['temp_data'] = {}

    # --- BOOKING FLOW ---
    if 'book' in lower_msg:
        session['booking_stage'] = 'from'
        session['temp_data'] = {}
        response = "Sure! Please tell me your departure city."

    elif session['booking_stage'] == 'from':
        suggested = validate_city(msg)
        if suggested and suggested.lower() != lower_msg:
            session['temp_data']['city_suggestion_type'] = 'from'
            session['temp_data']['suggested_city'] = suggested
            session['booking_stage'] = 'confirm_city'
            response = f"Did you mean '{suggested}' as your departure city? (yes/no)"
        elif suggested:
            session['temp_data']['from'] = suggested
            session['booking_stage'] = 'to'
            response = "Got it. Now tell me your destination city."
        else:
            response = "I couldn't find that city. Please enter a valid Indian city."

    elif session['booking_stage'] == 'to':
        suggested = validate_city(msg)
        if suggested and suggested.lower() != lower_msg:
            session['temp_data']['city_suggestion_type'] = 'to'
            session['temp_data']['suggested_city'] = suggested
            session['booking_stage'] = 'confirm_city'
            response = f"Did you mean '{suggested}' as your destination city? (yes/no)"
        elif suggested:
            session['temp_data']['to'] = suggested
            session['booking_stage'] = 'flight_number'
            response = "Please provide your flight number."
        else:
            response = "I couldn't find that city. Please enter a valid Indian city."

    elif session['booking_stage'] == 'confirm_city':
        if lower_msg in ['yes', 'y']:
            city_type = session['temp_data']['city_suggestion_type']
            session['temp_data'][city_type] = session['temp_data']['suggested_city']

            if city_type == 'from':
                session['booking_stage'] = 'to'
                response = "Got it. Now tell me your destination city."
            else:
                session['booking_stage'] = 'flight_number'
                response = "Please provide your flight number."
        else:
            city_type = session['temp_data']['city_suggestion_type']
            session['booking_stage'] = city_type
            response = f"Okay, please re-enter your correct {city_type} city."

    elif session['booking_stage'] == 'flight_number':
        session['temp_data']['flight_number'] = msg.upper()
        session['booking_stage'] = 'date'
        response = "Enter your flight date (YYYY-MM-DD)."

    elif session['booking_stage'] == 'date':
        try:
            flight_date = datetime.strptime(msg, '%Y-%m-%d').date()
            data = session['temp_data']
            data['date'] = str(flight_date)
            booking_id = generate_booking_id()
            data['booking_id'] = booking_id
            data['status'] = 'On Time'
            flights[booking_id] = data
            session['booking_stage'] = None
            response = (
                f"Flight booked successfully!\n"
                f"Booking ID: {booking_id}\n"
                f"From: {data['from']} → To: {data['to']}\n"
                f"Flight: {data['flight_number']}\n"
                f"Date: {data['date']}"
            )
        except ValueError:
            response = "Please enter a valid date in YYYY-MM-DD format."

    # --- CANCEL FLIGHT ---
    elif 'cancel' in lower_msg:
        session['booking_stage'] = 'cancel'
        response = "Please provide your booking ID to cancel the flight."

    elif session['booking_stage'] == 'cancel':
        booking_id = msg.upper()
        if booking_id in flights:
            flight = flights.pop(booking_id)
            response = (
                f"Flight {flight['flight_number']} from {flight['from']} → {flight['to']} "
                f"on {flight['date']} has been cancelled."
            )
        else:
            response = "Invalid booking ID. Please check and try again."
        session['booking_stage'] = None

    # --- CHECK STATUS ---
    elif 'status' in lower_msg or 'check' in lower_msg:
        session['booking_stage'] = 'status'
        response = "Please provide your booking ID to check the flight status."

    elif session['booking_stage'] == 'status':
        booking_id = msg.upper()
        if booking_id in flights:
            info = flights[booking_id]
            response = (
                f"Flight Status:\n"
                f"Booking ID: {booking_id}\n"
                f"From: {info['from']} → To: {info['to']}\n"
                f"Flight: {info['flight_number']}\n"
                f"Date: {info['date']}\n"
                f"Status: {info['status']}"
            )
        else:
            response = "Invalid booking ID or flight not found."
        session['booking_stage'] = None

    # --- POLICY QUESTIONS ---
    elif any(k in lower_msg for k in POLICY_KB.keys()) or "policy" in lower_msg:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        questions = list(POLICY_KB.keys())
        answers = list(POLICY_KB.values())
        vectorizer = TfidfVectorizer().fit_transform(questions + [lower_msg])
        similarity = cosine_similarity(vectorizer[-1], vectorizer[:-1])
        best_idx = similarity.argmax()
        score = similarity[0][best_idx]
        response = answers[best_idx] if score > 0.1 else (
            "You can ask about baggage, refund, cancellation, or meals for more information."
        )

    else:
        response = (
            "I can help you with:\n"
            "- Booking a flight\n"
            "- Cancelling a flight\n"
            "- Checking flight status\n"
            "- Airline policy questions"
        )

    return jsonify({"response": response})


if __name__ == '__main__':
    app.run(debug=True)
