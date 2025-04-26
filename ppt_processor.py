import json
import boto3
import os
import tempfile
import base64
import requests
import time
from datetime import datetime
import logging
from decimal import Decimal
import secrets

# 配置日志
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 自定义JSON编码器
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(DecimalEncoder, self).default(obj)

# 初始化AWS服务客户端
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# 环境变量
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'your-ppt-review-bucket')
REVIEW_STATUS_TABLE = os.environ.get('REVIEW_STATUS_TABLE', 'PPTReviewStatus')
CONTENT_REVIEWER_FUNCTION = os.environ.get('CONTENT_REVIEWER_FUNCTION')
IMAGE_FORMAT = os.environ.get('IMAGE_FORMAT', 'jpg')
IMAGE_WIDTH = int(os.environ.get('IMAGE_WIDTH', '1920'))
IMAGE_HEIGHT = int(os.environ.get('IMAGE_HEIGHT', '1080'))

# Aspose Cloud API 配置
ASPOSE_CLIENT_ID = os.environ.get('ASPOSE_CLIENT_ID', '')
ASPOSE_CLIENT_SECRET = os.environ.get('ASPOSE_CLIENT_SECRET', '')
ASPOSE_BASE_URL = "https://api.aspose.cloud/v3.0"

# LibreOffice路径
LIBREOFFICE_PATH = '/opt/lo/instdir/program/soffice'

def lambda_handler(event, context):
    """Lambda处理函数"""
    try:
        logger.info(f"收到事件: {json.dumps(event)}")
        
        # 处理API Gateway请求
        if 'requestContext' in event:
            http_method = event.get('requestContext', {}).get('http', {}).get('method', '')
            path = event.get('rawPath', '')
            
            if http_method == 'OPTIONS':
                return create_response(200, {'message': 'OK'})
                
            if path.endswith('/upload') and http_method == 'POST':
                return handle_upload(event)
            elif path.endswith('/status') and http_method == 'GET':
                return handle_status(event)
            else:
                return create_response(404, {'error': '未知的请求路径'})
                
        # 处理S3事件
        elif 'Records' in event and event['Records'][0].get('eventSource') == 'aws:s3':
            process_s3_event(event)
            return
            
        else:
            return create_response(400, {'error': '未知的事件类型'})
            
    except Exception as e:
        logger.error(f"处理请求时出错: {str(e)}")
        return create_response(500, {'error': str(e)})

def handle_status(event):
    """处理状态查询请求"""
    try:
        logger.info("=================== 状态查询开始 ===================")
        logger.info(f"完整事件: {json.dumps(event, cls=DecimalEncoder)}")
        
        # 获取查询参数
        if 'queryStringParameters' not in event or not event['queryStringParameters']:
            logger.error("缺少查询参数")
            return create_response(400, {
                'status': 'error',
                'message': '缺少必要的查询参数'
            })
            
        params = event['queryStringParameters']
        s3_key = params.get('s3_key')
        
        if not s3_key:
            logger.error("缺少s3_key参数")
            return create_response(400, {
                'status': 'error',
                'message': '缺少必要的s3_key参数'
            })
            
        logger.info(f"查询状态: s3_key={s3_key}")
        
        try:
            # 从DynamoDB获取状态
            status_data = get_status(s3_key)
            
            if not status_data:
                logger.error(f"未找到状态数据: {s3_key}")
                return create_response(404, {
                    'status': 'error',
                    'message': '未找到指定文件的状态信息'
                })
            
            logger.info("=================== DynamoDB数据 ===================")
            logger.info(f"原始状态数据: {json.dumps(status_data, cls=DecimalEncoder)}")
            
            # 检查results字段
            if 'results' in status_data:
                logger.info("=================== 审核结果数据 ===================")
                if isinstance(status_data['results'], str):
                    try:
                        parsed_results = json.loads(status_data['results'])
                        logger.info("成功解析results字符串")
                        logger.info(f"解析后的results: {json.dumps(parsed_results, cls=DecimalEncoder)}")
                    except json.JSONDecodeError as e:
                        logger.error(f"解析results字符串失败: {str(e)}")
                        logger.error(f"原始results字符串: {status_data['results']}")
                else:
                    logger.info(f"results是对象类型: {type(status_data['results'])}")
                    logger.info(f"results内容: {json.dumps(status_data['results'], cls=DecimalEncoder)}")
            
            # 构建响应
            response = create_response(200, status_data)
            logger.info("=================== API响应 ===================")
            logger.info(f"响应内容: {json.dumps(response, cls=DecimalEncoder)}")
            logger.info("=================== 状态查询结束 ===================")
            
            return response
            
        except Exception as e:
            logger.error(f"获取状态信息时出错: {str(e)}")
            logger.exception("详细错误信息:")
            return create_response(500, {
                'status': 'error',
                'message': f'获取状态信息失败: {str(e)}'
            })
            
    except Exception as e:
        logger.error(f"处理状态查询请求时出错: {str(e)}")
        logger.exception("详细错误信息:")
        return create_response(500, {
            'status': 'error',
            'message': f'服务器内部错误: {str(e)}'
        })

def handle_upload(event):
    """处理文件上传请求"""
    try:
        if 'body' not in event:
            return create_response(400, {'error': '缺少请求体'})
            
        # 解析请求体
        body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        if 'file' not in body or 'fileName' not in body:
            return create_response(400, {'error': '缺少必要参数'})
            
        file_content = body['file']
        file_name = body['fileName'].lower()
        custom_prompt = body.get('prompt', '')
        
        try:
            file_data = base64.b64decode(file_content)
        except Exception as e:
            return create_response(400, {'error': 'Base64解码失败'})
            
        # 生成唯一的S3键
        timestamp = int(time.time())
        random_suffix = secrets.token_hex(4)
        s3_key = f"{timestamp}_{random_suffix}_{file_name}"
        
        # 确定文件类型和处理方式
        is_ppt = file_name.endswith(('.ppt', '.pptx'))
        is_image = file_name.endswith(('.jpg', '.jpeg', '.png'))
        
        if not (is_ppt or is_image):
            return create_response(400, {'error': '不支持的文件类型'})
            
        # 更新状态为接收
        update_status(s3_key, 'RECEIVED')
        
        try:
            if is_ppt:
                # 上传原始PPT文件
                s3.put_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=f"{s3_key}/original",
                    Body=file_data,
                    ContentType='application/octet-stream'
                )
                
                # 处理PPT文件
                logger.info(f"开始处理PPT文件: {s3_key}")
                update_status(s3_key, 'PROCESSING')
                images_info = process_with_aspose_cloud(s3_key, S3_BUCKET_NAME)
                
                # 保存处理结果
                content_key = f"{s3_key}/content_info.json"
                s3.put_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=content_key,
                    Body=json.dumps(images_info),
                    ContentType='application/json'
                )
                
            else:  # 图片文件
                # 确定内容类型
                content_type = 'image/jpeg' if file_name.endswith(('.jpg', '.jpeg')) else 'image/png'
                
                # 上传图片文件
                s3.put_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=s3_key,
                    Body=file_data,
                    ContentType=content_type
                )
                
                # 准备图片信息
                image_info = {
                    'source_file': s3_key,
                    'content_type': content_type,
                    'file_size': len(file_data),
                    'upload_time': datetime.now().isoformat(),
                    'processing_method': 'direct_image'
                }
                
                # 保存内容信息
                content_key = f"{s3_key}/content_info.json"
                s3.put_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=content_key,
                    Body=json.dumps(image_info),
                    ContentType='application/json'
                )
            
            # 更新状态为等待审核
            update_status(s3_key, 'WAITING_REVIEW')
            
            # 调用内容审核函数
            if CONTENT_REVIEWER_FUNCTION:
                response = lambda_client.invoke(
                    FunctionName=CONTENT_REVIEWER_FUNCTION,
                    InvocationType='Event',  # 异步调用
                    Payload=json.dumps({
                        's3_key': s3_key,
                        'bucket_name': S3_BUCKET_NAME,
                        'content_key': content_key,
                        'custom_prompt': custom_prompt
                    })
                )
                logger.info(f"已触发内容审核: {s3_key}")
            
            return create_response(200, {
                'status': 'success',
                'message': '文件上传成功，开始处理',
                's3_key': s3_key
            })
            
        except Exception as e:
            error_msg = f"处理文件时出错: {str(e)}"
            logger.error(error_msg)
            update_status(s3_key, 'ERROR', {'error': str(e)})
            return create_response(500, {'error': error_msg})
            
    except Exception as e:
        logger.error(f"处理上传请求时出错: {str(e)}")
        return create_response(500, {'error': str(e)})

def get_aspose_access_token():
    """获取Aspose Cloud API访问令牌"""
    auth_url = "https://api.aspose.cloud/connect/token"
    auth_data = {
        "grant_type": "client_credentials",
        "client_id": ASPOSE_CLIENT_ID,
        "client_secret": ASPOSE_CLIENT_SECRET
    }
    
    response = requests.post(auth_url, data=auth_data)
    if response.status_code != 200:
        raise Exception(f"获取Aspose访问令牌失败: {response.text}")
    
    return response.json()["access_token"]

def process_with_aspose_cloud(s3_key, bucket_name):
    """使用Aspose.Slides Cloud API转换PPT为图片"""
    try:
        logger.info(f"开始使用Aspose Cloud处理PPT: {s3_key}")
        
        # 获取访问令牌
        access_token = get_aspose_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # 获取原始PPT文件
        response = s3.get_object(Bucket=bucket_name, Key=f"{s3_key}/original")
        ppt_content = response['Body'].read()
        
        # 上传到Aspose Cloud
        storage_api_url = f"{ASPOSE_BASE_URL}/slides/storage/file/temp.pptx"
        upload_response = requests.put(
            storage_api_url,
            headers={"Authorization": f"Bearer {access_token}"},
            data=ppt_content
        )
        
        if upload_response.status_code != 200:
            raise Exception(f"上传到Aspose失败: {upload_response.text}")
            
        # 获取幻灯片数量
        info_response = requests.get(
            f"{ASPOSE_BASE_URL}/slides/temp.pptx/info",
            headers=headers
        )
        
        if info_response.status_code != 200:
            raise Exception(f"获取幻灯片信息失败: {info_response.text}")
            
        slide_count = info_response.json().get("slidesCount", 0)
        image_files = []
        
        # 处理每张幻灯片
        for slide_index in range(1, slide_count + 1):
            convert_url = f"{ASPOSE_BASE_URL}/slides/temp.pptx/slides/{slide_index}/{IMAGE_FORMAT}"
            convert_params = {
                "width": IMAGE_WIDTH,
                "height": IMAGE_HEIGHT
            }
            
            convert_response = requests.get(
                convert_url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=convert_params
            )
            
            if convert_response.status_code != 200:
                logger.error(f"转换幻灯片 {slide_index} 失败")
                continue
                
            # 上传转换后的图片到S3
            image_key = f"{s3_key}/images/slide_{slide_index}.{IMAGE_FORMAT}"
            s3.put_object(
                Bucket=bucket_name,
                Key=image_key,
                Body=convert_response.content,
                ContentType=f'image/{IMAGE_FORMAT}'
            )
            
            image_files.append(image_key)
            logger.info(f"已处理幻灯片 {slide_index}")
            
        # 删除Aspose上的临时文件
        requests.delete(
            storage_api_url,
            headers=headers
        )
        
        # 返回处理结果
        return {
            "source_file": s3_key,
            "format": IMAGE_FORMAT,
            "image_count": len(image_files),
            "images": image_files,
            "width": IMAGE_WIDTH,
            "height": IMAGE_HEIGHT,
            "processing_method": "aspose-cloud",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Aspose处理失败: {str(e)}")
        raise

def update_status(s3_key, status, results=None):
    """更新处理状态"""
    table = dynamodb.Table(REVIEW_STATUS_TABLE)
    timestamp = int(time.time())
    
    item = {
        's3_key': s3_key,
        'status': status,
        'timestamp': timestamp,
        'last_updated': datetime.now().isoformat()
    }
    
    if results:
        item['results'] = results
    
    table.put_item(Item=item)

def get_status(s3_key):
    """获取处理状态"""
    try:
        table = dynamodb.Table(REVIEW_STATUS_TABLE)
        response = table.get_item(Key={'s3_key': s3_key})
        return response.get('Item')
    except Exception as e:
        logger.error(f"获取状态失败: {str(e)}")
        return None

def create_response(status_code, body):
    """创建API Gateway响应"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }

def handle_review_result(event):
    """处理审核结果查询请求"""
    try:
        logger.info("=================== 审核结果查询开始 ===================")
        logger.info(f"完整事件: {json.dumps(event, cls=DecimalEncoder)}")
        
        # 获取查询参数
        if 'queryStringParameters' not in event or not event['queryStringParameters']:
            logger.error("缺少查询参数")
            return create_response(400, {
                'status': 'error',
                'message': '缺少必要的查询参数'
            })
            
        params = event['queryStringParameters']
        s3_key = params.get('s3_key')
        
        if not s3_key:
            logger.error("缺少s3_key参数")
            return create_response(400, {
                'status': 'error',
                'message': '缺少必要的s3_key参数'
            })
            
        logger.info(f"查询审核结果: s3_key={s3_key}")
        
        try:
            # 从S3获取审核结果
            response = s3.get_object(
                Bucket=S3_BUCKET_NAME,
                Key=f"{s3_key}/review_result.json"
            )
            review_result = json.loads(response['Body'].read().decode('utf-8'))
            
            logger.info("=================== S3审核结果 ===================")
            logger.info(f"审核结果: {json.dumps(review_result, cls=DecimalEncoder)}")
            
            # 获取DynamoDB中的状态信息
            status_data = get_status(s3_key)
            
            # 合并结果
            full_result = {
                'status': 'success',
                'processing_status': status_data.get('status') if status_data else 'UNKNOWN',
                'timestamp': status_data.get('timestamp') if status_data else None,
                'review_result': review_result
            }
            
            logger.info("=================== 完整响应 ===================")
            logger.info(f"响应内容: {json.dumps(full_result, cls=DecimalEncoder)}")
            logger.info("=================== 审核结果查询结束 ===================")
            
            return create_response(200, full_result)
            
        except s3.exceptions.NoSuchKey:
            logger.error(f"未找到审核结果文件: {s3_key}/review_result.json")
            return create_response(404, {
                'status': 'error',
                'message': '未找到审核结果文件'
            })
        except Exception as e:
            logger.error(f"获取审核结果时出错: {str(e)}")
            logger.exception("详细错误信息:")
            return create_response(500, {
                'status': 'error',
                'message': f'获取审核结果失败: {str(e)}'
            })
            
    except Exception as e:
        logger.error(f"处理审核结果查询请求时出错: {str(e)}")
        logger.exception("详细错误信息:")
        return create_response(500, {
            'status': 'error',
            'message': f'服务器内部错误: {str(e)}'
        })

def process_s3_event(event):
    """处理S3事件"""
    try:
        # 从S3事件中获取信息
        for record in event['Records']:
            bucket_name = record['s3']['bucket']['name']
            s3_key = record['s3']['object']['key']
            
            # 更新状态为处理中
            update_status(s3_key, 'PROCESSING')
            
            # 获取图片信息
            response = s3.head_object(Bucket=bucket_name, Key=s3_key)
            image_info = {
                'file_size': response['ContentLength'],
                'last_modified': response['LastModified'].isoformat(),
                'content_type': response.get('ContentType', 'image/jpeg')
            }
            
            # 构建内容信息
            content_info = {
                'source_file': s3_key,
                'file_info': image_info,
                'content_type': image_info['content_type'],
                'processing_method': 'direct_image',
                'timestamp': datetime.now().isoformat()
            }
            
            # 保存内容信息
            content_key = f"{s3_key}/content_info.json"
            s3.put_object(
                Bucket=bucket_name,
                Key=content_key,
                Body=json.dumps(content_info, cls=DecimalEncoder),
                ContentType='application/json'
            )
            
            logger.info(f"已保存内容信息到 {content_key}")
            
            # 如果没有设置内容审核函数，直接标记为完成
            if not CONTENT_REVIEWER_FUNCTION:
                update_status(s3_key, 'COMPLETED', content_info)
                logger.info(f"未配置内容审核函数，处理完成: {s3_key}")
                return
            
            # 更新状态为等待审核
            update_status(s3_key, 'WAITING_REVIEW')
            
            logger.info(f"图片处理完成，等待内容审核: {s3_key}")
            
    except Exception as e:
        error_msg = f"处理S3事件时出错: {str(e)}"
        logger.error(error_msg)
        if 's3_key' in locals():
            update_status(s3_key, 'ERROR', {'error': error_msg})

def handle_status(event):
    """处理状态查询请求"""
    try:
        if 'queryStringParameters' not in event or not event['queryStringParameters']:
            return create_response(400, {'error': '缺少查询参数'})
            
        s3_key = event['queryStringParameters'].get('s3_key')
        if not s3_key:
            return create_response(400, {'error': '缺少s3_key参数'})
            
        status = get_status(s3_key)
        if not status:
            return create_response(404, {'error': '未找到状态信息'})
            
        return create_response(200, status)
        
    except Exception as e:
        logger.error(f"处理状态查询请求时出错: {str(e)}")
        return create_response(500, {'error': '处理请求时出错'}) 