#!/usr/bin/env python
"""
批量替换main.py中的AIAgent调用
将 AIAgent(api_key=self.api_key, model=self.model) 替换为 self._create_ai_agent()
"""

import re
import os

def main():
    file_path = "main.py"
    if not os.path.exists(file_path):
        print(f"错误: 文件 {file_path} 不存在")
        return
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 模式1: 直接替换 AIAgent(api_key=self.api_key, model=self.model)
    old_pattern = r'AIAgent\(api_key=self\.api_key,\s*model=self\.model\)'
    new_text = r'self._create_ai_agent()'
    
    new_content, count1 = re.subn(old_pattern, new_text, content)
    
    # 模式2: 替换 AIAgent(api_key=self.api_key, model=self.model) 可能有空格变化
    old_pattern2 = r'AIAgent\(\s*api_key\s*=\s*self\.api_key\s*,\s*model\s*=\s*self\.model\s*\)'
    new_content, count2 = re.subn(old_pattern2, new_text, new_content)
    
    # 模式3: 简单替换，捕获常见变体
    old_pattern3 = r'AIAgent\(api_key\s*=\s*self\.api_key\s*,\s*model\s*=\s*self\.model\)'
    new_content, count3 = re.subn(old_pattern3, new_text, new_content)
    
    total = count1 + count2 + count3
    
    if total > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"替换完成！共替换 {total} 处")
        
        # 统计剩余的 AIAgent( 调用
        remaining = len(re.findall(r'AIAgent\(', new_content))
        print(f"剩余 AIAgent( 调用: {remaining}")
        
        # 检查是否还有 api_key 参数
        api_key_calls = len(re.findall(r'api_key\s*=', new_content))
        print(f"剩余 api_key= 参数: {api_key_calls}")
    else:
        print("未找到需要替换的调用")

if __name__ == "__main__":
    main()