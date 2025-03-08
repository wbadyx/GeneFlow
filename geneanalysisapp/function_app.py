import azure.functions as func
import logging
import uuid
from azure.storage.blob import BlobServiceClient
import os
import json
import datetime
from azure.batch import BatchServiceClient
from azure.batch.batch_auth import SharedKeyCredentials
from azure.batch.models import JobAddParameter, PoolInformation, TaskAddParameter
from azure.storage.blob import generate_blob_sas, BlobSasPermissions, generate_container_sas, ContainerSasPermissions
import traceback
from azure.communication.email import EmailClient


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="upload_function")
def upload_function(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed an upload request.')
    
    try:
        # 从环境变量获取连接字符串
        connection_string = os.environ["STORAGE_CONNECTION_STRING"]
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # 生成唯一任务ID
        job_id = str(uuid.uuid4())
        
        # 获取上传的文件
        file_data = req.get_body()
        email = req.params.get('email', os.environ.get("ADMIN_EMAIL"))
        
        # 获取容器客户端
        container_client = blob_service_client.get_container_client("rawsequences")
        
        # 上传文件到blob
        blob_name = f"{job_id}/input.fq.gz"
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(file_data)
        
        # 创建任务元数据
        metadata = {
            "jobId": job_id,
            "status": "uploaded",
            "userEmail": email,
            "createdAt": datetime.datetime.utcnow().isoformat()
        }
        
        # 保存元数据
        metadata_blob = container_client.get_blob_client(f"{job_id}/metadata.json")
        metadata_blob.upload_blob(json.dumps(metadata))
        
        # 返回成功响应
        return func.HttpResponse(
            json.dumps({"jobId": job_id, "status": "uploaded"}),
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error processing upload: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.event_grid_trigger(arg_name="azeventgrid")
def trigger_analysis(azeventgrid: func.EventGridEvent):
    # 解析事件数据
    data = azeventgrid.get_json()
    
    # 确保这是一个 blob 创建事件
    if azeventgrid.event_type != 'Microsoft.Storage.BlobCreated':
        logging.info(f"Ignoring event type: {azeventgrid.event_type}")
        return
    
    # 获取 blob URL
    url = data.get('url', '')
    if not url:
        logging.error("No URL found in event data")
        return
    
    # 从 URL 中提取 blob 路径
    # URL 格式: https://<storage-account>.blob.core.windows.net/<container>/<path>
    url_parts = url.replace('https://', '').split('/')
    container_name = url_parts[1]
    blob_path = '/'.join(url_parts[2:])
    
    # 确认这是我们感兴趣的容器和 blob 格式
    if container_name != 'rawsequences' or not blob_path.endswith('input.fq.gz'):
        logging.info(f"Ignoring blob: {container_name}/{blob_path}")
        return
    
    logging.info(f"Python EventGrid trigger processing a blob: {blob_path}")

    job_id = None
    try:
        # 解析路径获取任务ID
        job_id = blob_path.split('/')[0]  # {job_id}/input.fq.gz
        logging.info(f"Processing job ID: {job_id}")
        
        # 检查必要的环境变量
        required_env_vars = [
            "STORAGE_CONNECTION_STRING", 
            "BATCH_ACCOUNT_NAME", 
            "BATCH_ACCOUNT_KEY", 
            "BATCH_ACCOUNT_URL", 
            "BATCH_POOL_ID"
        ]
        
        missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
        if missing_vars:
            raise ValueError(f"缺少必要的环境变量: {', '.join(missing_vars)}")
        
        # 连接到Blob存储
        connection_string = os.environ["STORAGE_CONNECTION_STRING"]
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # 从连接字符串中提取账户名和密钥
        conn_parts = {p.split('=')[0]: p.split('=', 1)[1] for p in connection_string.split(';') if '=' in p}
        account_name = conn_parts.get('AccountName')
        account_key = conn_parts.get('AccountKey')
        
        if not account_name or not account_key:
            raise ValueError("无法从连接字符串中提取存储账户名称或密钥")
            
        logging.info(f"Using storage account: {account_name}")
        
        raw_container_client = blob_service_client.get_container_client("rawsequences")
        refs_container_client = blob_service_client.get_container_client("refs")
        results_container_client = blob_service_client.get_container_client("results")

        # 读取元数据文件
        metadata_blob = raw_container_client.get_blob_client(f"{job_id}/metadata.json")
        metadata_content = metadata_blob.download_blob().readall().decode('utf-8')
        metadata = json.loads(metadata_content)

        # 更新任务状态
        metadata["status"] = "processing"
        metadata["startTime"] = datetime.datetime.utcnow().isoformat()

        # 保存更新的元数据
        metadata_blob.upload_blob(json.dumps(metadata), overwrite=True)
        logging.info(f"Updated metadata for job {job_id}")
        
        # 配置Batch客户端
        batch_account_name = os.environ["BATCH_ACCOUNT_NAME"]
        batch_account_key = os.environ["BATCH_ACCOUNT_KEY"]
        batch_account_url = os.environ["BATCH_ACCOUNT_URL"]
        batch_pool_id = os.environ["BATCH_POOL_ID"]
        
        logging.info(f"Connecting to Batch service with account: {batch_account_name}")
        logging.info(f"Batch URL: {batch_account_url}")
        # 不要记录完整的密钥，但可以记录一部分用于调试
        masked_key = batch_account_key[:4] + "..." + batch_account_key[-4:] if len(batch_account_key) > 8 else "***"
        logging.info(f"Using Batch account key (masked): {masked_key}")
        
        try:
            credentials = SharedKeyCredentials(batch_account_name, batch_account_key)
            batch_client = BatchServiceClient(credentials, batch_url=batch_account_url)
            # 测试连接 - 获取池列表
            pools = list(batch_client.pool.list())
            logging.info(f"Successfully connected to Batch service. Found {len(pools)} pools.")
            
            # 验证池是否存在
            pool_exists = False
            for pool in pools:
                if pool.id == batch_pool_id:
                    pool_exists = True
                    logging.info(f"Found specified pool: {batch_pool_id}")
                    break
            
            if not pool_exists:
                logging.warning(f"Specified pool '{batch_pool_id}' not found in account. Available pools: {[p.id for p in pools]}")
        except Exception as batch_conn_error:
            logging.error(f"Failed to connect to Batch service: {str(batch_conn_error)}")
            raise ValueError(f"Batch服务连接失败，请检查账户凭据: {str(batch_conn_error)}")
        
        # 创建Batch任务
        job = JobAddParameter(
            id=job_id,
            pool_info=PoolInformation(pool_id=batch_pool_id)
        )

        # 尝试添加作业（如果已存在则忽略）
        try:
            batch_client.job.add(job)
            logging.info(f"Created new batch job: {job_id}")
        except Exception as e:
            if 'JobExists' not in str(e):
                raise
            logging.info(f"Job {job_id} already exists")
        
        # 创建SAS URLs for input
        input_blob = raw_container_client.get_blob_client(f"{job_id}/input.fq.gz")
        # 使用正确的方式生成 SAS 令牌，使用从连接字符串提取的账户名和密钥
        input_sas = generate_blob_sas(
            account_name=account_name,
            container_name="rawsequences",
            blob_name=f"{job_id}/input.fq.gz",
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=2)
        )
        input_url = f"{input_blob.url}?{input_sas}"
        logging.info(f"Generated input file SAS URL")
        
        # 构建下载参考文件的命令
        ref_download_commands = ""
        blob_list = list(refs_container_client.list_blobs())
        logging.info(f"Found {len(blob_list)} reference files")
        
        for blob in blob_list:
            blob_client = refs_container_client.get_blob_client(blob.name)
            # 使用正确的方式生成 SAS 令牌，使用从连接字符串提取的账户名和密钥
            ref_sas = generate_blob_sas(
                account_name=account_name,
                container_name="refs",
                blob_name=blob.name,
                account_key=account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=2)
            )
            ref_url = f"{blob_client.url}?{ref_sas}"
            ref_download_commands += f"wget -O ref/{blob.name} \"{ref_url}\" && "

        # 创建任务命令
        command = f"""#!/bin/bash
set -e
# 使用 Batch 节点上已存在的工作目录
cd $AZ_BATCH_TASK_WORKING_DIR
echo "Current working directory: $(pwd)"

# 下载输入文件
echo "Downloading input file..."
wget -O input.fq.gz "{input_url}"
ls -la input.fq.gz

# 创建参考目录
mkdir -p ref
echo "Created reference directory"

# 下载参考文件
echo "Downloading reference files..."
{ref_download_commands}
ls -la ref/

# 运行分析
echo "Running BWA alignment..."
bwa mem -t 2 -k 32 -M ref/chrY.fa input.fq.gz | samtools view -bS - | samtools sort -m 100M - -o output_result.sort.bam
echo "BWA alignment completed"

# 生成结果文件
echo "Generating result file..."
samtools view output_result.sort.bam > output_result.xls
gzip -f output_result.xls
ls -la output_result.xls.gz
echo "Analysis completed successfully"
"""

        # 生成结果容器的 SAS
        results_sas = generate_container_sas(
            account_name=account_name,
            container_name="results",
            account_key=account_key,
            permission=ContainerSasPermissions(write=True),
            expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        )
        # 添加任务
        task = TaskAddParameter(
            id=f"{job_id}-task",
            command_line=f"/bin/bash -c '{command}'",  # 修改为使用 /bin/bash -c 执行命令
            output_files=[
                {
                    "file_pattern": "$AZ_BATCH_TASK_WORKING_DIR/output_result.xls.gz",  # 修改文件路径
                    "destination": {
                        "container": {
                            "path": f"{job_id}/output_result.xls.gz",  # 修改为完整的目标文件路径
                            "container_url": f"https://{account_name}.blob.core.windows.net/results?{results_sas}"
                        }
                    },
                    "upload_options": {"upload_condition": "taskSuccess"}
                }
            ]
        )
        batch_client.task.add(job_id=job_id, task=task)
        logging.info(f"Successfully submitted batch task for job {job_id}")

    except Exception as e:
        error_message = str(e)
        stack_trace = traceback.format_exc()
        logging.error(f"Error triggering analysis: {error_message}")
        logging.error(f"Stack trace: {stack_trace}")
        
        try:
            # 更新任务状态为失败
            if job_id:
                connection_string = os.environ.get("STORAGE_CONNECTION_STRING")
                if connection_string:
                    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
                    raw_container_client = blob_service_client.get_container_client("rawsequences")

                    metadata_blob = raw_container_client.get_blob_client(f"{job_id}/metadata.json")
                    if metadata_blob.exists():
                        metadata_content = metadata_blob.download_blob().readall().decode('utf-8')
                        metadata = json.loads(metadata_content)

                        metadata["status"] = "error"
                        metadata["error"] = error_message
                        metadata["errorTime"] = datetime.datetime.utcnow().isoformat()

                        metadata_blob.upload_blob(json.dumps(metadata), overwrite=True)
                        logging.info(f"Updated metadata with error status for job {job_id}")
        except Exception as metadata_error:
            logging.error(f"Failed to update metadata with error status: {str(metadata_error)}")


@app.event_grid_trigger(arg_name="azeventgrid")
def process_results(azeventgrid: func.EventGridEvent):
    # 解析事件数据
    data = azeventgrid.get_json()
    
    # 确保这是一个 blob 创建事件
    if azeventgrid.event_type != 'Microsoft.Storage.BlobCreated':
        logging.info(f"忽略事件类型: {azeventgrid.event_type}")
        return
    
    # 获取 blob URL
    url = data.get('url', '')
    if not url:
        logging.error("事件数据中未找到 URL")
        return
    
    # 从 URL 中提取 blob 路径
    # URL 格式: https://<storage-account>.blob.core.windows.net/<container>/<path>
    url_parts = url.replace('https://', '').split('/')
    container_name = url_parts[1]
    blob_path = '/'.join(url_parts[2:])
    
    # 确认这是我们感兴趣的容器和 blob 格式
    if container_name != 'results' or not (blob_path.endswith('_result.xls.gz') or blob_path.endswith('_result.csv.gz')):
        logging.info(f"忽略 blob: {container_name}/{blob_path}")
        return
    
    logging.info(f"Python EventGrid 触发器处理结果文件: {blob_path}")

    try:
        # 解析路径获取任务ID
        job_id = blob_path.split('/')[0]  # 格式: {job_id}/output_result.xls.gz
        logging.info(f"处理任务 ID: {job_id}")
        
        # 连接到Blob存储
        connection_string = os.environ["STORAGE_CONNECTION_STRING"]
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)

        # 从连接字符串中提取账户名和密钥
        conn_parts = {p.split('=')[0]: p.split('=', 1)[1] for p in connection_string.split(';') if '=' in p}
        account_name = conn_parts.get('AccountName')
        account_key = conn_parts.get('AccountKey')
        
        if not account_name or not account_key:
            raise ValueError("无法从连接字符串中提取存储账户名称或密钥")

        # 读取原始元数据
        raw_container_client = blob_service_client.get_container_client("rawsequences")
        metadata_blob = raw_container_client.get_blob_client(f"{job_id}/metadata.json")
        metadata_content = metadata_blob.download_blob().readall().decode('utf-8')
        metadata = json.loads(metadata_content)

        # 更新任务状态
        metadata["status"] = "completed"
        metadata["endTime"] = datetime.datetime.utcnow().isoformat()

        # 计算运行时间
        start_time = datetime.datetime.fromisoformat(metadata["startTime"])
        end_time = datetime.datetime.fromisoformat(metadata["endTime"])
        duration = (end_time - start_time).total_seconds()
        metadata["durationSeconds"] = duration

        # 更新元数据
        metadata_blob.upload_blob(json.dumps(metadata), overwrite=True)

        # 生成结果文件的SAS URL - 使用正确的方法
        results_container_client = blob_service_client.get_container_client("results")
        result_blob = results_container_client.get_blob_client(blob_path)
        
        # 使用独立的 generate_blob_sas 函数生成 SAS 令牌
        result_sas = generate_blob_sas(
            account_name=account_name,
            container_name="results",
            blob_name=blob_path,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.datetime.utcnow() + datetime.timedelta(days=7)
        )
        result_url = f"{result_blob.url}?{result_sas}"

        # 确定文件类型
        file_type = "XLS" if blob_path.endswith('_result.xls.gz') else "CSV"

        # 使用Azure Communication Services发送邮件
        email_client = EmailClient.from_connection_string(
            os.environ["COMMUNICATION_SERVICES_CONNECTION_STRING"]
        )

        from_email = os.environ["FROM_EMAIL"]
        to_email = metadata.get("userEmail", os.environ["ADMIN_EMAIL"])

        email_content = f'''
        <h2>您的基因分析任务已完成!</h2>
        <p><strong>任务ID:</strong> {job_id}</p>
        <p><strong>开始时间:</strong> {metadata["startTime"]}</p>
        <p><strong>完成时间:</strong> {metadata["endTime"]}</p>
        <p><strong>运行时长:</strong> {duration:.2f} 秒</p>
        <p>您可以通过以下链接下载分析结果:</p>
        <p><a href="{result_url}">下载{file_type}文件</a></p>
        <p>此链接将在7天后过期。</p>
        '''

        # 检查 EmailClient 的可用方法
        logging.info(f"EmailClient 可用方法: {dir(email_client)}")
        
        # 创建消息对象作为字典
        message = {
            "senderAddress": from_email,
            "recipients": {
                "to": [{"address": to_email}]
            },
            "content": {
                "subject": f'基因分析结果 - 任务 {job_id}',
                "html": email_content
            }
        }
        
        # 发送邮件
        poller = email_client.begin_send(message=message)
        result = poller.result()
        logging.info(f"邮件已发送，消息ID: {result.message_id if hasattr(result, 'message_id') else '未知'}")

    except Exception as e:
        error_message = str(e)
        logging.error(f"处理结果时出错: {error_message}")
        logging.error(f"错误详情: {traceback.format_exc()}")
        
        # 发送错误通知邮件
        try:
            email_client = EmailClient.from_connection_string(
                os.environ["COMMUNICATION_SERVICES_CONNECTION_STRING"]
            )
            from_email = os.environ["FROM_EMAIL"]
            admin_email = os.environ["ADMIN_EMAIL"]

            error_content = f'''
            <h2>基因分析任务处理结果时出错</h2>
            <p><strong>错误信息:</strong> {error_message}</p>
            <p><strong>时间:</strong> {datetime.datetime.utcnow().isoformat()}</p>
            '''

            # 创建错误消息对象作为字典
            error_message_obj = {
                "senderAddress": from_email,
                "recipients": {
                    "to": [{"address": admin_email}]
                },
                "content": {
                    "subject": f'错误通知 - 任务 {job_id if "job_id" in locals() else "未知"}',
                    "html": error_content
                }
            }
            
            # 发送错误邮件
            poller = email_client.begin_send(message=error_message_obj)
            result = poller.result()
            logging.info(f"错误通知邮件已发送，消息ID: {result.message_id if hasattr(result, 'message_id') else '未知'}")
                
        except Exception as email_error:
            logging.error(f"发送错误邮件失败: {str(email_error)}")
            logging.error(f"错误邮件错误详情: {traceback.format_exc()}")
