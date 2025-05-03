# lambda/index.py
import json
import os
import boto3
import re  # 正規表現モジュールをインポート
from botocore.exceptions import ClientError
import requests


# Lambda コンテキストからリージョンを抽出する関数
def extract_region_from_arn(arn):
    # ARN 形式: arn:aws:lambda:region:account-id:function:function-name
    match = re.search('arn:aws:lambda:([^:]+):', arn)
    if match:
        return match.group(1)
    return "ap-northeast-1"  # デフォルト値

# グローバル変数としてクライアントを初期化（初期値）
bedrock_client = None

# モデルID
MODEL_ID = os.environ.get("MODEL_ID", "amazon.nova-lite-v1:0")

NGROK_URL = os.environ.get("NGROK_URL","https://7988-34-142-255-108.ngrok-free.app" )
GENERATE_PATH = "/generate"
full_url = NGROK_URL.rstrip("/") + GENERATE_PATH

def lambda_handler(event, context):
    try:
        # コンテキストから実行リージョンを取得し、クライアントを初期化
        global bedrock_client
        if bedrock_client is None:
            region = extract_region_from_arn(context.invoked_function_arn)
            bedrock_client = boto3.client('bedrock-runtime', region_name=region)
            print(f"Initialized Bedrock client in region: {region}")
        
        print("Received event:", json.dumps(event))
        
        # Cognitoで認証されたユーザー情報を取得
        user_info = None
        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            user_info = event['requestContext']['authorizer']['claims']
            print(f"Authenticated user: {user_info.get('email') or user_info.get('cognito:username')}")
        
        # リクエストボディの解析
        body = json.loads(event['body'])
        message = body['message']
        conversation_history = body.get('conversationHistory', [])
        
        print("Processing message:", message)
        print("Using model:", MODEL_ID)
        
        # 会話履歴を使用
        messages = conversation_history.copy()
        
        # ユーザーメッセージを追加
        messages.append({
            "role": "user",
            "content": message
        })
        
        # Nova Liteモデル用のリクエストペイロードを構築
        # 会話履歴を含める
        bedrock_messages = []
        for msg in messages:
            if msg["role"] == "user":
                bedrock_messages.append({
                    "role": "user",
                    "content": [{"text": msg["content"]}]
                })
            elif msg["role"] == "assistant":
                bedrock_messages.append({
                    "role": "assistant", 
                        "content": [{"text": msg["content"]}]
                    })
            
            # invoke_model用のリクエストペイロード
            
               # Build the FastAPI payload exactly as in your curl example:
        request_payload = {
            "prompt": message,
            "max_new_tokens": 512,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9
        }
        print("Calling FastAPI /generate with payload:", json.dumps(request_payload))
        
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
        }
        # If API Gateway passed an Authorization header, forward it to FastAPI
        auth = event.get("headers", {}).get("authorization")
        if auth:
            headers["Authorization"] = auth
        
        # Call your FastAPI /generate endpoint
        response = requests.post(
            full_url,
            headers=headers,
            json=request_payload
        )
        
        # レスポンスを解析
        response_body = response.json()
        print("FastAPI response:", json.dumps(response_body, ensure_ascii=False))
        
        # Example response validation
        if "generated_text" not in response_body:
            raise Exception("No 'generated_text' in FastAPI response")
        
        # アシスタントの応答を取得
        assistant_response = response_body["generated_text"]
            
        # アシスタントの応答を会話履歴に追加
        messages.append({
            "role": "assistant",
            "content": assistant_response
        })
        
        # 成功レスポンスの返却
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
        print("Error:", str(error))
        
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": str(error)
            })
        }
