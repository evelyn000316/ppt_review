#!/bin/bash

# 显示帮助信息
show_help() {
  echo "PPT审核系统部署脚本"
  echo ""
  echo "用法: $0 [选项]"
  echo ""
  echo "选项:"
  echo "  -h, --help      显示帮助信息"
  echo "  -i, --infra     仅部署基础设施堆栈"
  echo "  -a, --app       仅部署应用堆栈"
  echo "  --all           部署所有堆栈 (默认行为)"
  echo ""
  exit 0
}

# 部署基础设施堆栈
deploy_infra() {
  echo "正在部署基础设施堆栈..."
  sam deploy --config-file samconfig-infra.toml --template-file infra-template.yaml
  if [ $? -ne 0 ]; then
    echo "基础设施堆栈部署失败。"
    exit 1
  fi
  echo "基础设施堆栈部署完成。"
}

# 部署应用堆栈
deploy_app() {
  echo "正在部署应用堆栈..."
  sam deploy --config-file samconfig-app.toml --template-file app-template.yaml
  if [ $? -ne 0 ]; then
    echo "应用堆栈部署失败。"
    exit 1
  fi
  echo "应用堆栈部署完成。"
}

# 默认部署所有堆栈
deploy_all=true
deploy_infra_only=false
deploy_app_only=false

# 解析命令行参数
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      show_help
      ;;
    -i|--infra)
      deploy_infra_only=true
      deploy_all=false
      shift
      ;;
    -a|--app)
      deploy_app_only=true
      deploy_all=false
      shift
      ;;
    --all)
      deploy_all=true
      shift
      ;;
    *)
      echo "未知选项: $1"
      show_help
      ;;
  esac
done

# 执行部署
if $deploy_all; then
  deploy_infra
  deploy_app
elif $deploy_infra_only; then
  deploy_infra
elif $deploy_app_only; then
  deploy_app
fi

echo "部署完成。" 