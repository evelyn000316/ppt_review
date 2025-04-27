import json
import boto3
import os
from datetime import datetime
import logging
from decimal import Decimal
import base64

# 配置日志
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 自定义JSON编码器
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# 初始化AWS客户端
s3 = boto3.client('s3')
bedrock = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')

# 环境变量
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', "anthropic.claude-3-7-sonnet-20250219-v1:0")  # 使用用户指定的版本
REVIEW_STATUS_TABLE = os.environ.get('REVIEW_STATUS_TABLE', 'PPTReviewStatus')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')

def invoke_bedrock_model(content_info, custom_prompt=None):
    """调用Bedrock模型进行审核"""
    try:
        # 确定内容类型
        content_type = content_info.get('content_type', '')
        is_image = content_type.startswith('image/') or content_info.get('processing_method') == 'direct_image'
        
        logger.info(f"开始审核内容，类型: {'图片' if is_image else 'PPT'}")
        logger.info(f"内容信息: {json.dumps(content_info, cls=DecimalEncoder)}")
            
        logger.info(f"使用Bedrock模型: {BEDROCK_MODEL_ID}")
        
        # 获取图片内容
        if is_image:
            try:
                # 从S3获取图片
                image_key = content_info.get('source_file')
                if not image_key:
                    error_msg = "缺少图片文件路径"
                    logger.error(error_msg)
                    return {"error": error_msg}
                
                logger.info(f"正在从S3获取图片: {image_key}")
                response = s3.get_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=image_key
                )
                
                # 读取图片内容并转换为base64
                image_content = response['Body'].read()
                image_base64 = base64.b64encode(image_content).decode('utf-8')
                
                # 规范化媒体类型
                normalized_content_type = 'image/jpeg'  # 默认使用jpeg
                if content_type:
                    content_type_lower = content_type.lower()
                    if content_type_lower in ['image/jpeg', 'image/png', 'image/gif', 'image/webp']:
                        normalized_content_type = content_type_lower
                
                logger.info(f"使用媒体类型: {normalized_content_type}")
                
                # 构建多模态消息
                messages = [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': get_default_prompt(content_info)
                            },
                            {
                                'type': 'image',
                                'source': {
                                    'type': 'base64',
                                    'media_type': normalized_content_type,
                                    'data': image_base64
                                }
                            }
                        ]
                    }
                ]
                
                logger.info("已准备多模态消息")
                
            except Exception as e:
                error_msg = f"处理图片时出错: {str(e)}"
                logger.error(error_msg)
                return {"error": error_msg}
        else:
            # 使用普通文本消息
            messages = [
                {
                    'role': 'user',
                    'content': get_default_prompt(content_info)
                }
            ]
        
        # 构建请求体
        request_body = {
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': 2000,
            'temperature': 0.1,
            'messages': messages
        }
        
        logger.info("正在调用Bedrock模型进行内容审核...")
        logger.info(f"Bedrock请求体: {json.dumps(request_body, cls=DecimalEncoder)}")
        
        try:
            # 调用Bedrock
            response = bedrock.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps(request_body)
            )

            
            # 读取响应
            response_body = json.loads(response['body'].read().decode())
            logger.info(f"Bedrock原始响应: {json.dumps(response_body, cls=DecimalEncoder)}")
            
            if 'content' not in response_body or not response_body['content']:
                error_msg = "Bedrock返回的响应中没有content字段"
                logger.error(error_msg)
                return {"error": error_msg}
                
            content = response_body['content'][0]['text']
            logger.info(f"Bedrock返回的文本内容: {content}")

            # 构建审核结果
            result = {
                "overall_result": {
                    "status": "PASS",  # 默认通过，除非发现问题
                    "summary": "图片审核完成"
                },
                "detailed_review": {
                    "personal_info": {
                        "status": "通过",
                        "issues": [],
                        "details": {
                            "name_check": {"status": "通过", "details": "未发现个人姓名"},
                            "id_check": {"status": "通过", "details": "未发现病人ID"},
                            "photo_check": {"status": "通过", "details": "未发现面部照片"},
                            "contact_check": {"status": "通过", "details": "未发现联系方式"}
                        }
                    },
                    "content_compliance": {
                        "status": "通过",
                        "issues": [],
                        "details": {
                            "political_check": {"status": "通过", "details": "未发现敏感政治内容"},
                            "inappropriate_check": {"status": "通过", "details": "未发现不当内容"},
                            "confidential_check": {"status": "通过", "details": "未发现机密信息"},
                            "trademark_check": {"status": "通过", "details": "未发现未授权商标"}
                        }
                    },
                    "reference_standard": {
                        "status": "通过",
                        "issues": [],
                        "details": {
                            "pubmed_check": {"status": "通过", "details": "无需验证引用"},
                            "format_check": {"status": "通过", "details": "格式规范"},
                            "accuracy_check": {"status": "通过", "details": "内容准确"},
                            "copyright_check": {"status": "通过", "details": "未发现版权问题"}
                        }
                    },
                    "quality_standard": {
                        "status": "通过",
                        "issues": [],
                        "details": {
                            "clarity_check": {"status": "通过", "details": "图像清晰度良好"},
                            "watermark_check": {"status": "通过", "details": "未发现干扰元素"},
                            "professional_check": {"status": "通过", "details": "符合专业要求"},
                            "resolution_check": {"status": "通过", "details": "分辨率适合"}
                        }
                    }
                },
                "key_findings": [],
                "recommendations": []
            }

            # 根据Bedrock的响应更新结果
            content_lower = content.lower()
            
            # 检查是否提到任何问题
            issues_found = False
            
            # 检查个人信息问题
            if "个人" in content or "姓名" in content or "病人" in content or "照片" in content:
                result["detailed_review"]["personal_info"]["status"] = "不通过"
                result["detailed_review"]["personal_info"]["issues"].append("发现个人信息相关问题")
                issues_found = True
            
            # 检查内容合规问题
            if "政治" in content or "敏感" in content or "不当" in content or "机密" in content:
                result["detailed_review"]["content_compliance"]["status"] = "不通过"
                result["detailed_review"]["content_compliance"]["issues"].append("发现内容合规问题")
                issues_found = True
            
            # 检查引用规范问题
            if "引用" in content or "参考" in content or "版权" in content:
                result["detailed_review"]["reference_standard"]["status"] = "不通过"
                result["detailed_review"]["reference_standard"]["issues"].append("发现引用规范问题")
                issues_found = True
            
            # 检查质量规范问题
            if "清晰" in content or "模糊" in content or "水印" in content or "分辨率" in content:
                result["detailed_review"]["quality_standard"]["status"] = "不通过"
                result["detailed_review"]["quality_standard"]["issues"].append("发现图片质量问题")
                issues_found = True
            
            # 如果发现任何问题，更新整体结果
            if issues_found:
                result["overall_result"]["status"] = "FAIL"
                result["overall_result"]["summary"] = "审核发现问题，请查看详细信息"
            
            # 提取关键发现
            key_findings = []
            for line in content.split('\n'):
                line = line.strip()
                if line and len(line) > 10:  # 忽略太短的行
                    key_findings.append(line)
            result["key_findings"] = key_findings[:5]  # 最多保留5个关键发现
            
            # 提取建议
            recommendations = []
            for line in content.split('\n'):
                line = line.strip()
                if "建议" in line or "推荐" in line:
                    recommendations.append(line)
            result["recommendations"] = recommendations[:3]  # 最多保留3个建议
            
            logger.info(f"生成的审核结果: {json.dumps(result, cls=DecimalEncoder)}")
            return result

        except Exception as e:
            error_msg = f"处理响应时出错: {str(e)}"
            logger.error(error_msg)
            logger.error(f"原始内容: {content}")
            return {"error": error_msg}
            
    except Exception as e:
        error_msg = f"内容审核过程出错: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}

def get_default_prompt(content_info):
    """获取默认提示词模板"""
    content_type_str = '图片' if content_info.get('content_type', '').startswith('image/') else 'PPT'
    content_info_str = json.dumps(content_info, ensure_ascii=False, indent=2, cls=DecimalEncoder)
    
    return f"""请对{content_type_str}内容进行详细审核。你必须对每个审核类别和子项进行具体评估，并在回复中详细说明每一项的审核结果。

===审核要求===
1. 个人信息审核 - 必须逐项检查并详细说明结果：
   - 个人姓名检查：是否出现中文名或拼音
   - 病人ID检查：是否存在门诊号或住院号
   - 面部照片检查：是否出现病人面部照片
   - 联系方式检查：是否暴露电话、邮箱等

2. 内容合规审核 - 必须逐项检查并详细说明结果：
   - 政治内容检查：是否包含敏感政治内容
   - 不当内容检查：是否包含不适宜的内容
   - 机密信息检查：是否包含商业机密或内部信息
   - 商标检查：是否包含未经授权的logo或商标

3. 引用规范审核 - 必须逐项检查并详细说明结果：
   - PubMed验证：引用内容是否能在PubMed上查证
   - 格式规范：引用格式是否符合学术规范
   - 内容准确性：引用内容是否准确反映原文
   - 版权合规：是否存在版权问题

4. 质量规范审核 - 必须逐项检查并详细说明结果：
   - 清晰度检查：图像清晰度是否达到专业标准
   - 干扰元素检查：是否存在影响观看的水印或干扰
   - 专业性检查：整体效果是否符合专业要求
   - 分辨率检查：图片分辨率是否适合展示用途

===回复要求===
1. 必须对每个审核类别的每个子项都给出具体的审核结果
2. 每个子项必须明确标注"通过"或"不通过"
3. 必须说明判断的具体依据
4. 如果不通过，必须说明具体问题
5. 总结时必须列举所有审核类别的结果


请按照以下格式返回审核结果：
{{
    "overall_result": {{
        "status": "PASS/FAIL",
        "summary": "总体审核结论（必须包含：总体结果、各类别结果统计、通过数量、不通过数量）"
    }},
    "detailed_review": {{
        "personal_info": {{
            "status": "通过/不通过",
            "issues": [],
            "details": {{
                "name_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明是否发现个人姓名及判断依据"
                }},
                "id_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明是否发现病人ID及判断依据"
                }},
                "photo_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明是否发现面部照片及判断依据"
                }},
                "contact_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明是否发现联系方式及判断依据"
                }}
            }}
        }},
        "content_compliance": {{
            "status": "通过/不通过",
            "issues": [],
            "details": {{
                "political_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明是否有敏感政治内容及判断依据"
                }},
                "inappropriate_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明是否有不适内容及判断依据"
                }},
                "confidential_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明是否有商业机密及判断依据"
                }},
                "trademark_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明是否有未授权商标及判断依据"
                }}
            }}
        }},
        "reference_standard": {{
            "status": "通过/不通过",
            "issues": [],
            "details": {{
                "pubmed_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明引用是否可查证及判断依据"
                }},
                "format_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明格式是否规范及判断依据"
                }},
                "accuracy_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明内容是否准确及判断依据"
                }},
                "copyright_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明是否有版权问题及判断依据"
                }}
            }}
        }},
        "quality_standard": {{
            "status": "通过/不通过",
            "issues": [],
            "details": {{
                "clarity_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明清晰度是否达标及判断依据"
                }},
                "watermark_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明是否有干扰元素及判断依据"
                }},
                "professional_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明专业性是否达标及判断依据"
                }},
                "resolution_check": {{
                    "status": "通过/不通过",
                    "details": "具体说明分辨率是否合适及判断依据"
                }}
            }}
        }}
    }},
    "key_findings": [
        "必须列出每个审核类别的主要发现",
        "包括所有通过和不通过的关键点"
    ],
    "recommendations": [
        "如有不通过项，必须提供具体的改进建议",
        "如全部通过，可以提供优化建议"
    ]
}}
"""

def update_status(s3_key, status, results=None):
    """更新处理状态"""
    logger.info("=================== 更新状态开始 ===================")
    logger.info(f"更新状态: {s3_key} -> {status}")
    
    try:
        status_table = dynamodb.Table(REVIEW_STATUS_TABLE)
        item = {
            's3_key': s3_key,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }
        
        if results:
            logger.info("=================== 审核结果数据 ===================")
            if isinstance(results, str):
                logger.info("结果是字符串类型")
                try:
                    # 尝试解析JSON字符串
                    parsed_results = json.loads(results)
                    logger.info("成功解析results字符串")
                    item['results'] = results
                except json.JSONDecodeError as e:
                    logger.error(f"解析results字符串失败: {str(e)}")
                    logger.error(f"原始results字符串: {results}")
                    item['results'] = results
            else:
                logger.info(f"结果是对象类型: {type(results)}")
                # 将对象转换为JSON字符串
                try:
                    item['results'] = json.dumps(results, cls=DecimalEncoder)
                    logger.info("成功将结果转换为JSON字符串")
                except Exception as e:
                    logger.error(f"转换结果为JSON字符串失败: {str(e)}")
                    logger.error(f"原始结果对象: {str(results)}")
                    item['results'] = str(results)
            
            logger.info(f"最终存储的结果: {item['results'][:200]}..." if len(item['results']) > 200 else item['results'])
        
        # 保存到DynamoDB
        logger.info("=================== DynamoDB更新 ===================")
        logger.info(f"保存的完整数据: {json.dumps(item, cls=DecimalEncoder)}")
        status_table.put_item(Item=item)
        logger.info("成功更新DynamoDB")
        logger.info("=================== 更新状态结束 ===================")
        
    except Exception as e:
        logger.error(f"更新状态失败: {str(e)}")
        logger.exception("详细错误信息:")

def lambda_handler(event, context):
    """Lambda处理函数"""
    logger.info(f"接收到事件: {json.dumps(event)}")
    
    try:
        # 获取参数
        s3_key = event.get('s3_key')
        bucket_name = event.get('bucket_name', S3_BUCKET_NAME)
        content_key = event.get('content_key')
        custom_prompt = event.get('custom_prompt')  # 获取自定义提示词
        
        # 更新状态为审核中
        update_status(s3_key, 'REVIEWING')
        
        # 获取内容信息
        try:
            response = s3.get_object(
                Bucket=bucket_name,
                Key=content_key
            )
            content_info = json.loads(response['Body'].read().decode('utf-8'))
        except Exception as e:
            error_msg = f"获取内容信息失败: {str(e)}"
            logger.error(error_msg)
            update_status(s3_key, 'ERROR', {'error': error_msg})
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'status': 'error',
                    'message': error_msg
                }, cls=DecimalEncoder)
            }
        
        # 调用Bedrock进行审核
        try:
            review_result = invoke_bedrock_model(content_info, custom_prompt)
            if 'error' in review_result:
                error_msg = f"Bedrock审核失败: {review_result['error']}"
                logger.error(error_msg)
                update_status(s3_key, 'ERROR', {'error': error_msg})
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'status': 'error',
                        'message': error_msg,
                        'type': 'bedrock_review_error'
                    }, cls=DecimalEncoder)
                }
        except Exception as e:
            error_msg = f"调用Bedrock模型失败: {str(e)}"
            logger.error(error_msg)
            update_status(s3_key, 'ERROR', {'error': error_msg})
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'status': 'error',
                    'message': error_msg,
                    'type': 'bedrock_api_error'
                }, cls=DecimalEncoder)
            }
        
        # 保存审核结果
        try:
            s3.put_object(
                Bucket=bucket_name,
                Key=f"{s3_key}/review_result.json",
                Body=json.dumps(review_result, cls=DecimalEncoder),
                ContentType='application/json'
            )
        except Exception as e:
            error_msg = f"保存审核结果失败: {str(e)}"
            logger.error(error_msg)
            # 继续执行，不影响状态更新
        
        # 更新状态为完成
        update_status(s3_key, 'COMPLETED', review_result)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'success',
                'results': review_result
            }, cls=DecimalEncoder)
        }
            
    except Exception as e:
        error_msg = f"处理失败: {str(e)}"
        logger.error(error_msg)
        if s3_key:
            update_status(s3_key, 'ERROR', {'error': error_msg})
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'message': error_msg
            }, cls=DecimalEncoder)
        } 