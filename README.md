# 基因序列分析平台 - GeneFlow
## 项目概述
GeneFlow 是一个基于 Azure 云服务的基因序列分析平台，允许用户上传 FASTQ 格式的测序数据，使用 BWA 与参考基因组进行比对，并通过邮件接收分析结果。该解决方案充分利用了 Azure 的多种服务，包括静态网站托管、Azure Functions、Blob Storage、Azure Batch 和 Communication Services，构建了一个完整的无服务器工作流。

## 系统架构
1. 前端界面 ：静态网页，用于用户上传测序数据
2. 数据存储 ：Azure Blob Storage 存储原始数据、参考基因组和分析结果
3. 计算处理 ：Azure Batch 执行大规模并行计算任务
4. 任务协调 ：Azure Functions 处理上传、触发分析和发送结果
5. 通知系统 ：Azure Communication Services 发送邮件通知
## 功能特点
- 简洁的用户界面，支持 FASTQ 格式文件上传
- 自动化的分析流程，无需用户干预
- 完整的任务日志记录，包括起始时间、结束时间和运行时长
- 分析完成后通过邮件发送结果下载链接
- 错误监控和通知机制 Azure 基因序列分析平台部署详细指南

以下是通过 Azure Portal 部署基因序列分析平台的详细步骤指南。

## 1. 创建资源组

1. 登录 [Azure Portal](https://portal.azure.com/)
2. 点击左侧菜单的"资源组"
3. 点击"创建"按钮
4. 填写以下信息：
   - 订阅：选择您的 Azure 订阅
   - 资源组名称：输入 `GeneFlowResourceGroup`
   - 区域：选择 `东亚` 或离您最近的区域
5. 点击"查看 + 创建"，然后点击"创建"

## 2. 创建存储账户

1. 在 Azure Portal 中，点击"创建资源"
2. 搜索并选择"存储账户"
3. 点击"创建"
4. 填写以下信息：
   - 订阅：选择您的 Azure 订阅
   - 资源组：选择 `GeneFlowResourceGroup`
   - 存储账户名称：输入 `geneflowstorage`（名称必须全局唯一）
   - 区域：选择与资源组相同的区域
   - 性能：选择"标准"
   - 冗余：选择"本地冗余存储 (LRS)"
5. 点击"查看 + 创建"，然后点击"创建"
6. 部署完成后，点击"前往资源"

### 2.1 创建 Blob 容器

1. 在存储账户页面，点击左侧菜单的"容器"（在"数据存储"部分）
2. 点击"+ 容器"
3. 创建以下三个容器：
   - 名称：`rawsequences`，公共访问级别：`私有`
   - 名称：`refs`，公共访问级别：`私有`
   - 名称：`results`，公共访问级别：`私有`

### 2.2 获取存储账户连接字符串

1. 在存储账户页面，点击左侧菜单的"访问密钥"（在"安全性 + 网络"部分）
2. 点击"显示密钥"
3. 复制"连接字符串"（通常是 `key1` 下方的连接字符串），保存到安全的地方，后续配置会用到

### 2.3 上传参考基因组文件

1. 解压 `ref.zip` 文件到本地文件夹
2. 在存储账户页面，点击左侧菜单的"容器"
3. 点击 `refs` 容器
4. 点击"上传"
5. 点击"浏览文件"，选择解压后的参考基因组文件
6. 点击"上传"

## 3. 设置 Azure Communication Services

1. 在 Azure Portal 中，点击"创建资源"
2. 搜索并选择"Communication Services"
3. 点击"创建"
4. 填写以下信息：
   - 订阅：选择您的 Azure 订阅
   - 资源组：选择 `GeneFlowResourceGroup`
   - 资源名称：输入 `geneflowcomm`
   - 数据位置：选择与资源组相同的区域
5. 点击"查看 + 创建"，然后点击"创建"
6. 部署完成后，点击"前往资源"

### 3.1 配置电子邮件服务

1. 在 Communication Services 资源页面，点击左侧菜单的"电子邮件"
2. 点击"开始使用"
3. 选择"使用 Azure 托管域"（使用 Azure 免费提供的托管域）
4. 在"发件人地址"中输入您想要的前缀（例如 `noreply`）
5. 域名将自动设置为 Azure 提供的免费域名（如 `*.azurecomm.net`）
6. 点击"创建"
7. 等待验证完成，状态变为"活动"

### 3.2 获取 Communication Services 连接字符串

1. 在 Communication Services 资源页面，点击左侧菜单的"密钥"
2. 复制"主连接字符串"，保存到安全的地方，后续配置会用到

## 4. 设置 Azure Batch 服务

1. 在 Azure Portal 中，点击"创建资源"
2. 搜索并选择"Batch 服务"
3. 点击"创建"
4. 填写以下信息：
   - 订阅：选择您的 Azure 订阅
   - 资源组：选择 `GeneFlowResourceGroup`
   - 账户名称：输入 `geneflowbatch`
   - 位置：选择与资源组相同的区域
   - 存储账户：选择之前创建的 `geneflowstorage`
5. 点击"查看 + 创建"，然后点击"创建"
6. 部署完成后，点击"前往资源"

### 4.1 创建计算池

1. 在 Batch 服务页面，点击左侧菜单的"池"
2. 点击"添加"
3. 填写以下信息：
   - 池 ID：输入 `geneflowpool`
   - 操作系统：选择 `Ubuntu Server 22.04-LTS`
   - 节点大小：选择 `Standard_D2s_v3`
   - 专用节点：设置为 `2`（或根据您的需求调整）
   - 低优先级节点：设置为 `0`
   - 启用自动缩放：根据需求选择
4. 在"启动任务"部分：
   - 命令行：输入 `/bin/bash -c "apt-get update && apt-get install -y bwa samtools && mkdir -p /mnt/batch/tasks/shared"`
   - 用户标识：选择"池用户"
   - 等待任务成功：选择"是"
5. 点击"确定"创建池

### 4.2 获取 Batch 账户密钥和 URL

1. 在 Batch 服务页面，点击左侧菜单的"密钥"
2. 复制"主密钥"和"URL"，保存到安全的地方，后续配置会用到

## 5. 创建 Function App

1. 在 Azure Portal 中，点击"创建资源"
2. 搜索并选择"Function App"
3. 点击"创建"
4. 填写以下信息：
   - 订阅：选择您的 Azure 订阅
   - 资源组：选择 `GeneFlowResourceGroup`
   - Function App 名称：输入 `geneanalysisapp`
   - 发布：选择"代码"
   - 运行时堆栈：选择 `Python`
   - 版本：选择 `3.11`
   - 区域：选择与资源组相同的区域
   - 操作系统：选择 `Linux`
   - 计划类型：选择"消耗（无服务器）"
5. 点击"查看 + 创建"，然后点击"创建"
6. 部署完成后，点击"前往资源"

### 5.1 配置 Function App 设置

1. 在 Function App 页面，点击左侧菜单的"配置"
2. 点击"新建应用程序设置"
3. 添加以下设置（每个设置都需要点击"新建应用程序设置"）：
   - 名称：`STORAGE_CONNECTION_STRING`，值：之前保存的存储账户连接字符串
   - 名称：`BATCH_ACCOUNT_NAME`，值：`geneflowbatch`
   - 名称：`BATCH_ACCOUNT_KEY`，值：之前保存的 Batch 账户主密钥
   - 名称：`BATCH_ACCOUNT_URL`，值：之前保存的 Batch URL
   - 名称：`BATCH_POOL_ID`，值：`geneflowpool`
   - 名称：`COMMUNICATION_SERVICES_CONNECTION_STRING`，值：之前保存的 Communication Services 连接字符串
   - 名称：`FROM_EMAIL`，值：您配置的发件人电子邮件地址（例如 `noreply@yourdomain.azurecomm.net`）
   - 名称：`ADMIN_EMAIL`，值：您的管理员电子邮件地址
4. 点击"保存"

### 5.2 部署 Function 代码

使用 Visual Studio Code 部署 Function 代码：

1. 确保已安装 [Visual Studio Code](https://code.visualstudio.com/) 和 [Azure Functions 扩展](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-azurefunctions)
2. 打开 VS Code，点击左侧的 Azure 图标
3. 在 Azure 扩展中，登录您的 Azure 账户
4. 在 FUNCTIONS 部分，找到您的订阅和 `geneanalysisapp` Function App
5. 右键点击 `geneanalysisapp`，选择"从工作区部署..."
6. 选择包含 Function 代码的文件夹（例如 `c:\Users\wba\Desktop\GeneFlow\geneanalysisapp`）
7. 确认部署
8. 等待部署完成，VS Code 会显示部署状态通知

## 6. 创建静态网页

### 6.1 启用存储账户的静态网站功能

1. 返回到 `geneflowstorage` 存储账户页面
2. 点击左侧菜单的"静态网站"（在"数据管理"部分）
3. 将"静态网站"设置为"已启用"
4. 索引文档名称：输入 `index.html`
5. 错误文档路径：输入 `index.html`
6. 点击"保存"
7. 记下"主终结点"URL，这将是您的网站地址

### 6.2 更新前端配置

1. 打开 `c:\Users\wba\Desktop\GeneFlow\gene-analysis-web\script.js` 文件
2. 将第 2 行的 `FUNCTION_APP_URL` 更新为您的 Function App URL（格式为 `https://geneanalysisapp.azurewebsites.net`）
3. 保存文件

### 6.3 上传前端文件

1. 在存储账户的"静态网站"页面，点击"$web"容器
2. 点击"上传"
3. 上传 `gene-analysis-web` 目录中的所有文件（`index.html`、`script.js` 和 `styles.css`）
4. 点击"上传"

## 7. 配置事件订阅

### 7.1 为原始数据容器创建事件订阅

1. 返回到 `geneflowstorage` 存储账户页面
2. 点击左侧菜单的"事件"
3. 点击"事件订阅"
4. 填写以下信息：
   - 名称：输入 `rawsequences-created`
   - 事件架构：选择"事件网格架构"
   - 系统主题名称：保持默认值
   - 筛选到事件类型：选择 `Blob Created`
   - 筛选到主题：`Subject Ends With`输入 `input.fq.gz`
   - 终结点类型：选择"Azure 函数"
   - 终结点：选择您的 Function App 和 `trigger_analysis` 函数
5. 点击"创建"

### 7.2 为结果容器创建事件订阅

1. 重复上述步骤，但使用以下不同的值：
   - 名称：输入 `results-created`
   - 筛选到主题：`Subject Ends With`输入 `_result.xls.gz`
   - 终结点：选择您的 Function App 和 `process_results` 函数
2. 点击"创建"

## 8. 验证部署

1. 访问之前记下的静态网站主终结点 URL
2. 输入您的电子邮件地址
3. 上传测试 FASTQ 文件（例如 `example/test.fq.gz`）
4. 点击"上传并分析"按钮
5. 验证上传是否成功，并记下任务 ID
6. 检查 Azure Portal 中的以下内容：
   - Blob 存储中是否有上传的文件
   - Batch 服务中是否创建了作业和任务
   - Function App 的日志是否显示处理过程
7. 等待分析完成，检查您的电子邮件是否收到结果通知
8. 点击邮件中的下载链接，验证是否可以下载结果文件

## 故障排除

如果在部署过程中遇到问题，请检查以下几点：

1. **Function App 日志**：在 Function App 页面，点击左侧菜单的"函数"，选择相应的函数，然后点击"监视"查看日志
2. **Batch 服务状态**：检查计算池是否正常运行
3. **事件订阅**：验证事件订阅是否正确配置
4. **应用程序设置**：确保所有必要的环境变量都已正确设置

完成以上步骤后，您的基因序列分析平台应该已经成功部署并可以使用了。用户可以通过静态网站上传测序数据，系统会自动处理并通过邮件发送结果。
