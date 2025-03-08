// 获取函数应用的URL
const FUNCTION_APP_URL = 'https://geneanalysisapp.azurewebsites.net';

// 上传文件函数
async function uploadFile() {
    const emailInput = document.getElementById('email');
    const fileInput = document.getElementById('sequenceFile');
    const statusDiv = document.getElementById('status');
    const spinner = document.getElementById('spinner');
    const uploadButton = document.getElementById('uploadButton');
    
    // 验证电子邮件
    if (!emailInput.value) {
        statusDiv.textContent = '请输入电子邮件地址';
        statusDiv.className = 'status error';
        return;
    }
    
    // 验证文件
    if (!fileInput.files || fileInput.files.length === 0) {
        statusDiv.textContent = '请选择一个文件';
        statusDiv.className = 'status error';
        return;
    }
    
    const file = fileInput.files[0];
    
    // 显示加载中
    statusDiv.textContent = '正在上传文件，请稍候...';
    statusDiv.className = 'status';
    spinner.style.display = 'block';
    uploadButton.disabled = true;
    
    try {
        // 创建带有查询参数的URL
        const uploadUrl = `${FUNCTION_APP_URL}/api/upload_function?email=${encodeURIComponent(emailInput.value)}`;
        
        // 发送文件
        const response = await fetch(uploadUrl, {
            method: 'POST',
            body: file
        });
        
        if (!response.ok) {
            throw new Error(`上传失败: ${response.status} ${response.statusText}`);
        }
        
        const result = await response.json();
        
        // 显示成功信息
        statusDiv.textContent = `上传成功！您的任务ID是: ${result.jobId}。分析完成后，结果将发送到您的邮箱。`;
        statusDiv.className = 'status success';
    } catch (error) {
        // 显示错误信息
        statusDiv.textContent = `错误: ${error.message}`;
        statusDiv.className = 'status error';
    } finally {
        // 隐藏加载中状态
        spinner.style.display = 'none';
        uploadButton.disabled = false;
    }
}

// 文件选择更新显示
document.getElementById('sequenceFile').addEventListener('change', function(e) {
    const fileName = e.target.files[0] ? e.target.files[0].name : '选择FASTQ文件';
    e.target.nextElementSibling.textContent = fileName;
});
