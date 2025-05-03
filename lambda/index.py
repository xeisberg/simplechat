# lambda/index.py
import json
import os
import requests
import traceback 

# Environment variables
NGROK_URL = os.environ.get("NGROK_URL", "https://b05b-34-16-222-244.ngrok-free.app") 
if not NGROK_URL:
    raise ValueError("NGROK_URL environment variable is not set!")

GENERATE_PATH = "/generate"
full_url = NGROK_URL.rstrip("/") + GENERATE_PATH

def lambda_handler(event, context):
    print("--- Lambda Execution Start ---")
    print(f"Function ARN: {context.invoked_function_arn}")
    print(f"Log stream name: {context.log_stream_name}")
    print("Received event:", json.dumps(event))

    try:
        user_info = None
        if 'requestContext' in event and 'authorizer' in event['requestContext'] and event['requestContext']['authorizer'] and 'claims' in event['requestContext']['authorizer']:
             user_info = event['requestContext']['authorizer']['claims']
             print(f"Authenticated user: {user_info.get('email') or user_info.get('cognito:username')}")
        else:
             print("No authenticated user info found in event.")

        try:
            if 'body' not in event or not event['body']:
                 raise ValueError("Request body is missing or empty.")
            body = json.loads(event['body'])
            message = body['message']
            conversation_history = body.get('conversationHistory', [])
            print("Parsed request body:", json.dumps(body))
            print("Received message:", message)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error parsing request body: {e}")
            return {
                "statusCode": 400, # Bad Request
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*", # Adjust CORS as needed
                },
                "body": json.dumps({"success": False, "error": f"Invalid request body: {e}"})
            }


        messages = conversation_history.copy()
        messages.append({"role": "user", "content": message})

        fastapi_payload = {
            "prompt": message,
            "max_new_tokens": 512,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9
        }

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AWS-Lambda-Function/1.0",
        }

        event_headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
        auth_header = event_headers.get("authorization")
        if auth_header:
            headers["Authorization"] = auth_header
            print("Forwarding Authorization header.")
        else:
            print("No Authorization header found in the incoming event.")


        print(f"Calling FastAPI endpoint: POST {full_url}")
        print("FastAPI request headers:", json.dumps(headers))
        print("FastAPI request payload:", json.dumps(fastapi_payload))

        response = None
        try:
            response = requests.post(
                full_url,
                headers=headers,
                json=fastapi_payload,
                timeout=30 
            )

            print(f"FastAPI response status code: {response.status_code}")
            print("FastAPI response headers:", json.dumps(dict(response.headers)))
            print("FastAPI raw response text:", response.text) 


            response.raise_for_status() 

            response_body = response.json()
            print("FastAPI parsed response JSON:", json.dumps(response_body, ensure_ascii=False))

            if "generated_text" not in response_body:
                print(f"Key 'generated_text' not found in FastAPI response: {response_body}")
                raise ValueError("Invalid response format from FastAPI: 'generated_text' key missing.")

            assistant_response = response_body["generated_text"]

        except requests.exceptions.Timeout:
            print(f"Error: Request to {full_url} timed out.")
            raise Exception("FastAPI endpoint timed out.") 
        except requests.exceptions.ConnectionError as e:
            print(f"Error: Could not connect to {full_url}. Error: {e}")
            raise Exception(f"FastAPI connection error: {e}") 
        except requests.exceptions.HTTPError as e:
    
            print(f"Error: FastAPI endpoint returned HTTP error: {e.response.status_code} {e.response.reason}")
 
            error_details = e.response.text[:500] 
            raise Exception(f"FastAPI HTTP error {e.response.status_code}. Response: {error_details}")
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON response from FastAPI.")

            raw_text = response.text[:500] if response else "N/A"
            raise Exception(f"FastAPI returned non-JSON response: {raw_text}") 
        except requests.exceptions.RequestException as e:

            print(f"Error: An error occurred during the request to FastAPI: {e}")
            raise Exception(f"FastAPI request failed: {e}")
        except ValueError as e:

             print(f"Error: {e}")
             raise 

        print("Successfully received and parsed response from FastAPI.")


        messages.append({
            "role": "assistant",
            "content": assistant_response
        })


        print("--- Lambda Execution Success ---")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*", 
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": True,
                "response": assistant_response,
                "conversationHistory": messages
            })
        }

    except Exception as error:
        print(f"!!! Lambda Handler Error: {type(error).__name__} - {error}")
 
        print("Stack Trace:")
        traceback.print_exc()
        print("--- Lambda Execution Failed ---")

        return {
            "statusCode": 500, 
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "success": False,

                "error": f"An internal server error occurred. Check logs for details. Error type: {type(error).__name__}"

            })
        }
