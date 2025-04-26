# PPT审核系统

这是一个基于AWS Serverless的PPT文件审核系统，支持PPT文件上传、内容提取与审核，并通过Amazon Bedrock提供智能内容分析。

## 功能特点

- PPT文件上传与处理
- 内容提取：文本与图片
- 幻灯片转换为图片
- 内容审核：隐私信息、引用文献、图片分析
- 实时状态查询
- 图片上传与审核

## 架构概述

系统采用了两个独立的CloudFormation堆栈:

### 基础设施堆栈
- S3存储桶：存储PPT文件和处理结果
- DynamoDB表：跟踪处理状态和审核结果

### 应用堆栈
- API Gateway：提供REST API接口
- Lambda函数：处理PPT文件和内容审核
- Lambda层：包含共享依赖
- IAM角色：授予必要权限

## 部署指南

系统部署被分为两个独立的堆栈，以避免循环依赖问题。

### 依赖项

- AWS CLI
- AWS SAM CLI
- Python 3.9+

### 准备工作

1. 创建Lambda层：

```bash
# 安装依赖到layer目录
python -m pip install -r requirements.txt -t layer/python/

# 创建层的ZIP文件
cd layer && zip -r ../lambda_layer.zip . && cd ..
```

### 部署方式

可以使用提供的部署脚本进行部署：

```bash
# 部署全部堆栈
./deploy.sh

# 仅部署基础设施堆栈
./deploy.sh --infra

# 仅部署应用堆栈
./deploy.sh --app
```

或者手动部署各个堆栈：

```bash
# 部署基础设施堆栈
sam deploy --config-file samconfig-infra.toml --template-file infra-template.yaml

# 部署应用堆栈
sam deploy --config-file samconfig-app.toml --template-file app-template.yaml
```

## API使用指南

### 文件上传

**请求**:
```
POST /upload
Content-Type: application/json
{
  "file": "base64编码的文件内容",
  "fileName": "example.pptx"
}
```

**响应**:
```json
{
  "status": "success",
  "message": "文件已接收并开始处理",
  "s3_key": "uploads/1623456789_example.pptx",
  "statusUrl": "/status?s3_key=uploads/1623456789_example.pptx"
}
```

### 状态查询

**请求**:
```
GET /status?s3_key=uploads/1623456789_example.pptx
```

**响应**:
```json
{
  "s3_key": "uploads/1623456789_example.pptx",
  "status": "COMPLETED",
  "timestamp": "2023-06-01T12:34:56",
  "results": {
    "overall_result": {
      "status": "PASS",
      "summary": "未发现隐私信息或引用问题"
    },
    "slide_results": [...]
  }
}
```

## 状态流程

- RECEIVED: 文件已接收
- PROCESSING: 正在处理PPT
- CONVERTED: PPT已转换为图片
- REVIEWING: 内容正在审核中
- COMPLETED: 审核完成
- ERROR: 处理失败

## 系统架构

系统使用以下AWS服务：
- AWS Lambda
- Amazon S3
- Amazon DynamoDB
- Amazon SQS
- Amazon Bedrock

## 前提条件

- AWS CLI已安装并配置
- AWS SAM CLI已安装
- Python 3.9或更高版本
- Node.js和npm（用于前端开发）

## 部署步骤

1. 克隆代码库：
```bash
git clone <repository-url>
cd ppt-review-system
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 部署到AWS：
```bash
sam build
sam deploy --guided
```

4. 配置环境变量：
- 复制`.env.example`为`.env`
- 更新环境变量值

## 本地开发

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 运行本地API：
```bash
sam local start-api
```

3. 运行前端：
```bash
cd frontend
python -m http.server 8000
```

## API文档

### 上传PPT
- 端点：POST /upload
- 请求体：multipart/form-data
- 响应：JSON包含任务ID

### 查询状态
- 端点：GET /status/{taskId}
- 响应：JSON包含处理状态和结果

## 配置说明

主要配置文件：
- template.yaml：AWS SAM模板
- .env：环境变量
- requirements.txt：Python依赖

## 许可证

MIT License 

### 使用方法

1. 打开前端页面
2. 输入API网关URL
3. 选择需要审核的内容类型：PPT或图片
4. 上传文件
5. 系统会自动处理文件并生成审核报告
6. 查看实时状态和最终审核结果

### PPT审核示例

1. PPT文件会被处理为多张图片，每张幻灯片一张图片
2. 系统审核每张幻灯片的内容，检查以下问题：
   - PII问题：个人信息、病人ID、联系方式等
   - 引用问题：引用文献是否存在、引用内容是否准确
   - 图片问题：是否包含客户logo、是否使用了品牌色

### 图片审核示例

1. 上传的图片文件会直接进入审核流程
2. 系统检查以下问题：
   - PII问题：图片中是否包含个人信息、病人ID、联系方式等
   - 敏感内容：是否包含敏感政治内容或不适宜的内容
   - 图片质量：清晰度是否满足要求，是否有水印或其他干扰元素

### 部署说明

#### 准备工作

1. 安装AWS CLI和SAM CLI
2. 配置AWS凭证

#### 部署步骤

1. 部署基础设施堆栈（S3桶和DynamoDB表）:
   ```
   ./deploy.sh --infra
   ```

2. 部署应用堆栈（Lambda函数和API网关）:
   ```
   ./deploy.sh --app
   ```

3. 获取API网关URL:
   ```
   aws cloudformation describe-stacks --stack-name ppt-review-app-dev --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' --output text
   ```

4. 在浏览器中打开前端页面，输入API网关URL

### 本地测试

可以使用提供的测试服务器在本地测试:

```
./start-test-server.sh
```

这将启动一个本地HTTP服务器，模拟API网关和Lambda函数的行为，并自动打开浏览器访问测试页面。

### 常见问题

1. **支持哪些文件格式？**
   - PPT文件：.ppt, .pptx
   - 图片文件：.jpg, .jpeg, .png, .gif

2. **文件大小限制是多少？**
   - API网关限制每个请求最大10MB
   - 如需上传更大的文件，建议使用预签名URL直接上传到S3

3. **处理时间需要多久？**
   - 取决于文件大小和幻灯片数量
   - 通常一个10页PPT文件需要1-3分钟完成全部处理和审核

4. **如何提高审核准确性？**
   - 可以在`content_reviewer.py`中调整提示模板
   - 可以使用更高级的Bedrock模型，如Claude 3 Opus

### 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 提交Pull Request 