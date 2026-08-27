import boto3
import json
import requests

# 리전 자동 감지
token = requests.put('http://169.254.169.254/latest/api/token', 
                   headers={'X-aws-ec2-metadata-token-ttl-seconds': '21600'}, 
                   timeout=1).text
region = requests.get('http://169.254.169.254/latest/meta-data/placement/region',
                    headers={'X-aws-ec2-metadata-token': token},
                    timeout=1).text

print(f'Region: {region}')
print()

bedrock = boto3.client('bedrock-runtime', region_name=region)

# Titan Embeddings test
print('=== Titan Embeddings Test ===')
try:
    response = bedrock.invoke_model(
        modelId='amazon.titan-embed-text-v2:0',
        body=json.dumps({
            'inputText': 'Hello test',
            'dimensions': 256,
            'normalize': True
        })
    )
    result = json.loads(response['body'].read())
    print(f'SUCCESS! Embedding dimensions: {len(result[\"embedding\"])}')
except Exception as e:
    print(f'FAILED: {e}')

# Cohere Multilingual test
print()
print('=== Cohere Multilingual Embeddings Test ===')
try:
    response = bedrock.invoke_model(
        modelId='cohere.embed-multilingual-v3',
        body=json.dumps({
            'texts': ['Hello test'],
            'input_type': 'search_document'
        })
    )
    result = json.loads(response['body'].read())
    print(f'SUCCESS! Embedding dimensions: {len(result[\"embeddings\"][0])}')
except Exception as e:
    print(f'FAILED: {e}')
