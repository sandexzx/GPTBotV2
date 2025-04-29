#!/bin/bash

# =============================================================================
# Telegram Bot Deployment Script
# =============================================================================
# This script automates the deployment of a Python Telegram bot to an Ubuntu server.
# It handles both new installations and updates, manages a virtual environment,
# creates systemd services, and provides backup/restore functionality.
#
# Usage: ./deploy_telegram_bot.sh [options]
#
# Options:
#   -h, --help             Display this help message
#   -i, --install          Force new installation mode
#   -u, --update           Force update mode
#   -r, --rollback [ver]   Rollback to a previous version (specify version or empty for latest backup)
#   -b, --backup-only      Only create a backup without making changes
#   -d, --debug            Enable debug mode with verbose output
#
# =============================================================================

# Set strict mode
set -e                 # Exit on error
set -o pipefail        # Exit on pipeline error

# =============================================================================
# Configuration Variables
# =============================================================================

# Default settings
DEPLOY_DIR="/opt/telegram_bot"
LOG_DIR="/var/log/telegram_bot"
BACKUP_DIR="/opt/telegram_bot_backups"
VENV_DIR="/opt/telegram_bot_venv"
MAX_BACKUPS=5
PROJECT_NAME="telegram_bot"
PYTHON_VERSION="3.12"
MAIN_FILE=""
SYSTEMD_SERVICE_NAME=""
GITHUB_REPO=""
GITHUB_BRANCH="main"

# Command-line options
INSTALL_MODE=""
UPDATE_MODE=""
ROLLBACK_VERSION=""
BACKUP_ONLY=false
DEBUG=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Current timestamp for backups
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Log file
LOG_FILE="/tmp/telegram_bot_deploy_${TIMESTAMP}.log"

# =============================================================================
# Helper Functions
# =============================================================================

# Function to print usage information
print_usage() {
    echo "Usage: $0 [options]"
    echo
    echo "Options:"
    echo "  -h, --help             Display this help message"
    echo "  -i, --install          Force new installation mode"
    echo "  -u, --update           Force update mode"
    echo "  -r, --rollback [ver]   Rollback to a previous version (specify version or empty for latest backup)"
    echo "  -b, --backup-only      Only create a backup without making changes"
    echo "  -d, --debug            Enable debug mode with verbose output"
    echo
    echo "Examples:"
    echo "  $0                     Auto-detect installation type"
    echo "  $0 --install           Force new installation"
    echo "  $0 --update            Force update mode"
    echo "  $0 --rollback          Rollback to most recent backup"
    echo "  $0 --rollback 20230415_120101  Rollback to specific backup"
}

# Function to log messages
log() {
    local level=$1
    local message=$2
    local color=$NC
    
    case $level in
        "INFO")
            color=$GREEN
            ;;
        "WARNING")
            color=$YELLOW
            ;;
        "ERROR")
            color=$RED
            ;;
        "DEBUG")
            color=$BLUE
            ;;
    esac
    
    echo -e "${color}[$(date +'%Y-%m-%d %H:%M:%S')] [${level}] ${message}${NC}"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [${level}] ${message}" >> "$LOG_FILE"
}

# Function to check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log "ERROR" "This script must be run as root"
        exit 1
    fi
}

# Function to parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                print_usage
                exit 0
                ;;
            -i|--install)
                INSTALL_MODE=true
                shift
                ;;
            -u|--update)
                UPDATE_MODE=true
                shift
                ;;
            -r|--rollback)
                if [[ -n $2 && ${2:0:1} != "-" ]]; then
                    ROLLBACK_VERSION=$2
                    shift
                else
                    ROLLBACK_VERSION="latest"
                fi
                shift
                ;;
            -b|--backup-only)
                BACKUP_ONLY=true
                shift
                ;;
            -d|--debug)
                DEBUG=true
                shift
                ;;
            *)
                log "ERROR" "Unknown option: $1"
                print_usage
                exit 1
                ;;
        esac
    done
    
    # Check for conflicting options
    if [[ "$INSTALL_MODE" == true && "$UPDATE_MODE" == true ]]; then
        log "ERROR" "Cannot specify both install and update modes"
        exit 1
    fi
    
    if [[ -n "$ROLLBACK_VERSION" && "$INSTALL_MODE" == true ]]; then
        log "ERROR" "Cannot specify both rollback and install modes"
        exit 1
    fi
    
    if [[ -n "$ROLLBACK_VERSION" && "$UPDATE_MODE" == true ]]; then
        log "ERROR" "Cannot specify both rollback and update modes"
        exit 1
    fi
}

# Function to create directories
create_directories() {
    local dirs=("$DEPLOY_DIR" "$LOG_DIR" "$BACKUP_DIR" "$VENV_DIR")
    
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            log "INFO" "Creating directory: $dir"
            mkdir -p "$dir"
        fi
    done
}

# Function to detect if the bot is already installed
detect_installation() {
    if [[ "$INSTALL_MODE" == true ]]; then
        log "INFO" "Forcing new installation mode"
        return 1
    elif [[ "$UPDATE_MODE" == true ]]; then
        log "INFO" "Forcing update mode"
        return 0
    fi
    
    if [[ -d "$DEPLOY_DIR" && -f "$DEPLOY_DIR/app.py" ]]; then
        log "INFO" "Detected existing installation"
        return 0
    else
        log "INFO" "No existing installation detected"
        return 1
    fi
}

# Function to detect the main Python file
detect_main_file() {
    log "INFO" "Detecting main Python file..."
    
    # Look for specific main file patterns
    for file in "$DEPLOY_DIR"/*.py; do
        if [[ -f "$file" ]]; then
            if grep -q "if __name__ == \"__main__\"" "$file"; then
                MAIN_FILE=$(basename "$file")
                log "INFO" "Found main file with __main__ check: $MAIN_FILE"
                return 0
            fi
        fi
    done
    
    # Look for files that might be the main one
    for name in "app.py" "main.py" "bot.py" "run.py" "start.py"; do
        if [[ -f "$DEPLOY_DIR/$name" ]]; then
            MAIN_FILE="$name"
            log "INFO" "Using likely main file: $MAIN_FILE"
            return 0
        fi
    done
    
    # If no main file found, use app.py as default or fail
    if [[ -f "$DEPLOY_DIR/app.py" ]]; then
        MAIN_FILE="app.py"
        log "WARNING" "No definitive main file found, using app.py as default"
        return 0
    else
        log "ERROR" "Could not determine main Python file"
        return 1
    fi
}

# Function to detect the project name
detect_project_name() {
    if [[ -d "$DEPLOY_DIR" ]]; then
        # Try to get project name from directory
        local dir_name=$(basename "$DEPLOY_DIR")
        if [[ "$dir_name" != "telegram_bot" ]]; then
            PROJECT_NAME="$dir_name"
            log "INFO" "Project name detected from directory: $PROJECT_NAME"
            return 0
        fi
        
        # If app.py exists, try to extract project name from it
        if [[ -f "$DEPLOY_DIR/app.py" ]]; then
            local app_name=$(grep -o "name.*=.*['\"].*['\"]" "$DEPLOY_DIR/app.py" | head -1 | cut -d'"' -f2 | cut -d"'" -f2)
            if [[ -n "$app_name" ]]; then
                PROJECT_NAME="$app_name"
                log "INFO" "Project name detected from app.py: $PROJECT_NAME"
                return 0
            fi
        fi
    fi
    
    # If we got here, use the default or the folder name
    PROJECT_NAME=$(basename "$DEPLOY_DIR")
    log "INFO" "Using default project name: $PROJECT_NAME"
    return 0
}

# Function to create a backup
create_backup() {
    if [[ ! -d "$DEPLOY_DIR" || ! -f "$DEPLOY_DIR/app.py" ]]; then
        log "WARNING" "No existing installation to backup"
        return 0
    fi
    
    local backup_file="${BACKUP_DIR}/${PROJECT_NAME}_${TIMESTAMP}.tar.gz"
    log "INFO" "Creating backup at: $backup_file"
    
    # Create the backup
    tar -czf "$backup_file" -C "$(dirname "$DEPLOY_DIR")" "$(basename "$DEPLOY_DIR")" 2>> "$LOG_FILE"
    
    # Also backup the venv if it exists
    if [[ -d "$VENV_DIR" ]]; then
        local venv_backup="${BACKUP_DIR}/${PROJECT_NAME}_venv_${TIMESTAMP}.tar.gz"
        log "INFO" "Creating virtual environment backup at: $venv_backup"
        tar -czf "$venv_backup" -C "$(dirname "$VENV_DIR")" "$(basename "$VENV_DIR")" 2>> "$LOG_FILE"
    fi
    
    # Also backup the systemd service if it exists
    if [[ -f "/etc/systemd/system/${PROJECT_NAME}.service" ]]; then
        local service_backup="${BACKUP_DIR}/${PROJECT_NAME}_service_${TIMESTAMP}.service"
        log "INFO" "Backing up systemd service file"
        cp "/etc/systemd/system/${PROJECT_NAME}.service" "$service_backup" 2>> "$LOG_FILE"
    fi
    
    # Save directory structure and file list
    find "$DEPLOY_DIR" -type f -name "*.py" | sort > "${BACKUP_DIR}/${PROJECT_NAME}_files_${TIMESTAMP}.txt"
    
    log "INFO" "Backup completed successfully"
    return 0
}

# Function to rotate backups
rotate_backups() {
    log "INFO" "Rotating backups, keeping last $MAX_BACKUPS"
    
    # Count project backup files
    local backup_count=$(ls -1 "${BACKUP_DIR}/${PROJECT_NAME}_"*.tar.gz 2>/dev/null | wc -l)
    
    # If we have more than MAX_BACKUPS, delete the oldest ones
    if [[ $backup_count -gt $MAX_BACKUPS ]]; then
        local excess=$((backup_count - MAX_BACKUPS))
        log "INFO" "Removing $excess old backups"
        
        # Remove the oldest backups
        ls -1t "${BACKUP_DIR}/${PROJECT_NAME}_"*.tar.gz | tail -n "$excess" | xargs rm -f
    fi
    
    # Do the same for venv backups
    local venv_backup_count=$(ls -1 "${BACKUP_DIR}/${PROJECT_NAME}_venv_"*.tar.gz 2>/dev/null | wc -l)
    if [[ $venv_backup_count -gt $MAX_BACKUPS ]]; then
        local venv_excess=$((venv_backup_count - MAX_BACKUPS))
        log "INFO" "Removing $venv_excess old venv backups"
        
        # Remove the oldest venv backups
        ls -1t "${BACKUP_DIR}/${PROJECT_NAME}_venv_"*.tar.gz | tail -n "$venv_excess" | xargs rm -f
    fi
    
    # And for service backups
    local service_backup_count=$(ls -1 "${BACKUP_DIR}/${PROJECT_NAME}_service_"*.service 2>/dev/null | wc -l)
    if [[ $service_backup_count -gt $MAX_BACKUPS ]]; then
        local service_excess=$((service_backup_count - MAX_BACKUPS))
        log "INFO" "Removing $service_excess old service backups"
        
        # Remove the oldest service backups
        ls -1t "${BACKUP_DIR}/${PROJECT_NAME}_service_"*.service | tail -n "$service_excess" | xargs rm -f
    fi
    
    # And for file lists
    local files_backup_count=$(ls -1 "${BACKUP_DIR}/${PROJECT_NAME}_files_"*.txt 2>/dev/null | wc -l)
    if [[ $files_backup_count -gt $MAX_BACKUPS ]]; then
        local files_excess=$((files_backup_count - MAX_BACKUPS))
        log "INFO" "Removing $files_excess old file lists"
        
        # Remove the oldest file lists
        ls -1t "${BACKUP_DIR}/${PROJECT_NAME}_files_"*.txt | tail -n "$files_excess" | xargs rm -f
    fi
}

# Function to install system dependencies
install_dependencies() {
    log "INFO" "Installing system dependencies"
    
    # Update package lists
    apt-get update -qq || {
        log "ERROR" "Failed to update package lists"
        return 1
    }
    
    # Install required packages
    apt-get install -y -qq python${PYTHON_VERSION} python${PYTHON_VERSION}-venv \
        python${PYTHON_VERSION}-dev python3-pip git curl ca-certificates \
        libpq-dev build-essential || {
        log "ERROR" "Failed to install required packages"
        return 1
    }
    
    log "INFO" "System dependencies installed successfully"
    return 0
}

# Function to setup virtual environment
setup_venv() {
    log "INFO" "Setting up Python virtual environment"
    
    # Create virtual environment if it doesn't exist
    if [[ ! -d "$VENV_DIR" ]]; then
        log "INFO" "Creating new virtual environment"
        python${PYTHON_VERSION} -m venv "$VENV_DIR" || {
            log "ERROR" "Failed to create virtual environment"
            return 1
        }
    else
        log "INFO" "Using existing virtual environment"
    fi
    
    # Upgrade pip
    source "${VENV_DIR}/bin/activate"
    pip install --upgrade pip -q || {
        log "WARNING" "Failed to upgrade pip, continuing anyway"
    }
    
    # Check if requirements.txt exists
    if [[ -f "${DEPLOY_DIR}/requirements.txt" ]]; then
        log "INFO" "Installing dependencies from requirements.txt"
        pip install -r "${DEPLOY_DIR}/requirements.txt" -q || {
            log "ERROR" "Failed to install dependencies"
            deactivate
            return 1
        }
    else
        log "WARNING" "No requirements.txt found, installing basic dependencies"
        pip install aiogram python-dotenv sqlalchemy -q || {
            log "ERROR" "Failed to install basic dependencies"
            deactivate
            return 1
        }
    fi
    
    # Install any additional dependencies that might be needed
    pip install psycopg2-binary pymongo -q || {
        log "WARNING" "Failed to install optional database dependencies, continuing anyway"
    }
    
    deactivate
    
    log "INFO" "Virtual environment setup completed"
    return 0
}

# Function to handle env file
handle_env_file() {
    # Check if .env file exists
    if [[ -f "${DEPLOY_DIR}/.env" ]]; then
        log "INFO" "Found existing .env file"
        return 0
    fi
    
    # Check if we need an .env file
    if grep -q "dotenv" "${DEPLOY_DIR}/app.py" || grep -q "os.getenv" "${DEPLOY_DIR}/app.py"; then
        log "INFO" "Application uses environment variables, creating .env file template"
        
        # Create basic .env file
        cat > "${DEPLOY_DIR}/.env" << EOL
# Telegram Bot Configuration
BOT_TOKEN=your_bot_token_here

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Database Configuration
# DB_URL=your_database_url_here
EOL
        
        log "WARNING" "Created .env file template. Please update with actual values."
        return 0
    fi
    
    log "INFO" "No need for .env file detected"
    return 0
}

# Function to preserve important files during update
preserve_files() {
    log "INFO" "Preserving important files"
    
    local temp_dir="/tmp/telegram_bot_preserve_${TIMESTAMP}"
    mkdir -p "$temp_dir"
    
    # Check for database files
    if [[ -f "${DEPLOY_DIR}/openai_bot.db" ]]; then
        log "INFO" "Preserving SQLite database file"
        cp "${DEPLOY_DIR}/openai_bot.db" "${temp_dir}/"
    fi
    
    # Check for .env file
    if [[ -f "${DEPLOY_DIR}/.env" ]]; then
        log "INFO" "Preserving .env file"
        cp "${DEPLOY_DIR}/.env" "${temp_dir}/"
    fi
    
    # Check for JSON files that might contain data
    if ls "${DEPLOY_DIR}"/*.json 1> /dev/null 2>&1; then
        log "INFO" "Preserving JSON files"
        cp "${DEPLOY_DIR}"/*.json "${temp_dir}/" 2>/dev/null || true
    fi
    
    # Check for any custom user files
    if [[ -d "${DEPLOY_DIR}/user_data" ]]; then
        log "INFO" "Preserving user_data directory"
        cp -r "${DEPLOY_DIR}/user_data" "${temp_dir}/"
    fi
    
    echo "$temp_dir"
}

# Function to restore preserved files
restore_preserved_files() {
    local temp_dir="$1"
    
    if [[ ! -d "$temp_dir" ]]; then
        log "WARNING" "No preserved files to restore"
        return 0
    fi
    
    log "INFO" "Restoring preserved files"
    
    # Restore database files
    if [[ -f "${temp_dir}/openai_bot.db" ]]; then
        log "INFO" "Restoring SQLite database file"
        cp "${temp_dir}/openai_bot.db" "${DEPLOY_DIR}/"
    fi
    
    # Restore .env file
    if [[ -f "${temp_dir}/.env" ]]; then
        log "INFO" "Restoring .env file"
        cp "${temp_dir}/.env" "${DEPLOY_DIR}/"
    fi
    
    # Restore JSON files
    if ls "${temp_dir}"/*.json 1> /dev/null 2>&1; then
        log "INFO" "Restoring JSON files"
        cp "${temp_dir}"/*.json "${DEPLOY_DIR}/" 2>/dev/null || true
    fi
    
    # Restore user_data directory
    if [[ -d "${temp_dir}/user_data" ]]; then
        log "INFO" "Restoring user_data directory"
        cp -r "${temp_dir}/user_data" "${DEPLOY_DIR}/"
    fi
    
    # Clean up temp directory
    rm -rf "$temp_dir"
    
    log "INFO" "File restoration completed"
    return 0
}

# Function to create or update systemd service
setup_systemd_service() {
    local service_file="/etc/systemd/system/${PROJECT_NAME}.service"
    log "INFO" "Setting up systemd service: ${PROJECT_NAME}.service"
    
    # Create service file
    cat > "$service_file" << EOL
[Unit]
Description=${PROJECT_NAME} Telegram Bot Service
After=network.target

[Service]
User=root
WorkingDirectory=${DEPLOY_DIR}
ExecStart=${VENV_DIR}/bin/python ${DEPLOY_DIR}/${MAIN_FILE}
Restart=always
RestartSec=10
StandardOutput=append:${LOG_DIR}/${PROJECT_NAME}.log
StandardError=append:${LOG_DIR}/${PROJECT_NAME}.log
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOL
    
    # Reload systemd daemon
    systemctl daemon-reload || {
        log "ERROR" "Failed to reload systemd daemon"
        return 1
    }
    
    # Enable service
    systemctl enable "${PROJECT_NAME}.service" || {
        log "ERROR" "Failed to enable ${PROJECT_NAME} service"
        return 1
    }
    
    log "INFO" "Systemd service setup completed"
    return 0
}

# Function to perform rollback
perform_rollback() {
    local version="$1"
    
    # Find backup file to restore
    local backup_file=""
    
    if [[ "$version" == "latest" ]]; then
        backup_file=$(ls -1t "${BACKUP_DIR}/${PROJECT_NAME}_"*.tar.gz 2>/dev/null | head -1)
        if [[ -z "$backup_file" ]]; then
            log "ERROR" "No backups found for rollback"
            return 1
        fi
        log "INFO" "Using latest backup for rollback: $(basename "$backup_file")"
    else
        backup_file="${BACKUP_DIR}/${PROJECT_NAME}_${version}.tar.gz"
        if [[ ! -f "$backup_file" ]]; then
            log "ERROR" "Backup file not found: $backup_file"
            return 1
        fi
        log "INFO" "Using specified backup for rollback: $(basename "$backup_file")"
    fi
    
    # Stop the service
    log "INFO" "Stopping ${PROJECT_NAME} service"
    systemctl stop "${PROJECT_NAME}.service" || {
        log "WARNING" "Failed to stop service, it might not be running"
    }
    
    # Create a backup of current state before rollback
    log "INFO" "Creating backup of current state before rollback"
    create_backup
    
    # Extract backup
    log "INFO" "Extracting backup"
    rm -rf "${DEPLOY_DIR}.rollback" 2>/dev/null || true
    mv "$DEPLOY_DIR" "${DEPLOY_DIR}.rollback" 2>/dev/null || true
    mkdir -p "$DEPLOY_DIR"
    
    tar -xzf "$backup_file" -C "$(dirname "$DEPLOY_DIR")" || {
        log "ERROR" "Failed to extract backup"
        mv "${DEPLOY_DIR}.rollback" "$DEPLOY_DIR" 2>/dev/null || true
        return 1
    }
    
    # Restore virtual environment if needed
    local venv_backup=""
    if [[ "$version" == "latest" ]]; then
        venv_backup=$(ls -1t "${BACKUP_DIR}/${PROJECT_NAME}_venv_"*.tar.gz 2>/dev/null | head -1)
    else
        venv_backup="${BACKUP_DIR}/${PROJECT_NAME}_venv_${version}.tar.gz"
    fi
    
    if [[ -f "$venv_backup" ]]; then
        log "INFO" "Restoring virtual environment from backup"
        rm -rf "${VENV_DIR}.rollback" 2>/dev/null || true
        mv "$VENV_DIR" "${VENV_DIR}.rollback" 2>/dev/null || true
        mkdir -p "$VENV_DIR"
        
        tar -xzf "$venv_backup" -C "$(dirname "$VENV_DIR")" || {
            log "ERROR" "Failed to restore virtual environment"
            mv "${VENV_DIR}.rollback" "$VENV_DIR" 2>/dev/null || true
            return 1
        }
    else
        log "INFO" "No virtual environment backup found, setting up new one"
        setup_venv
    fi
    
    # Restore systemd service if needed
    local service_backup=""
    if [[ "$version" == "latest" ]]; then
        service_backup=$(ls -1t "${BACKUP_DIR}/${PROJECT_NAME}_service_"*.service 2>/dev/null | head -1)
    else
        service_backup="${BACKUP_DIR}/${PROJECT_NAME}_service_${version}.service"
    fi
    
    if [[ -f "$service_backup" ]]; then
        log "INFO" "Restoring systemd service from backup"
        cp "$service_backup" "/etc/systemd/system/${PROJECT_NAME}.service"
        systemctl daemon-reload
    else
        log "INFO" "No service backup found, creating new service"
        detect_main_file
        setup_systemd_service
    fi
    
    # Start the service
    log "INFO" "Starting ${PROJECT_NAME} service"
    systemctl start "${PROJECT_NAME}.service" || {
        log "ERROR" "Failed to start service after rollback"
        return 1
    }
    
    log "INFO" "Rollback completed successfully"
    return 0
}

# Function to check service status
check_service_status() {
    log "INFO" "Checking service status"
    
    if systemctl is-active --quiet "${PROJECT_NAME}.service"; then
        log "INFO" "Service is active and running"
        systemctl status "${PROJECT_NAME}.service" --no-pager | grep -E "Active:|Main PID:" >> "$LOG_FILE"
    else
        log "WARNING" "Service is not running"
        systemctl status "${PROJECT_NAME}.service" --no-pager >> "$LOG_FILE" 2>&1 || true
    fi
}

# Function to display service management guide
display_service_guide() {
    echo -e "\n${GREEN}========== ${PROJECT_NAME} Telegram Bot Service Guide ==========${NC}"
    echo -e "${CYAN}Service has been installed as: ${PROJECT_NAME}.service${NC}"
    echo
    echo -e "${YELLOW}Basic Commands:${NC}"
    echo -e "  ${BLUE}Start the bot:${NC}     sudo systemctl start ${PROJECT_NAME}.service"
    echo -e "  ${BLUE}Stop the bot:${NC}      sudo systemctl stop ${PROJECT_NAME}.service"
    echo -e "  ${BLUE}Restart the bot:${NC}   sudo systemctl restart ${PROJECT_NAME}.service"
    echo -e "  ${BLUE}Check status:${NC}      sudo systemctl status ${PROJECT_NAME}.service"
    echo
    echo -e "${YELLOW}Log Management:${NC}"
    echo -e "  ${BLUE}View logs:${NC}         sudo journalctl -u ${PROJECT_NAME}.service"
    echo -e "  ${BLUE}Follow logs:${NC}       sudo journalctl -u ${PROJECT_NAME}.service -f"
    echo -e "  ${BLUE}Log file:${NC}          ${LOG_DIR}/${PROJECT_NAME}.log"
    echo
    echo -e "${YELLOW}Deployment:${NC}"
    echo -e "  ${BLUE}Update bot:${NC}        sudo $(readlink -f "$0") --update"
    echo -e "  ${BLUE}Rollback:${NC}          sudo $(readlink -f "$0") --rollback"
    echo -e "  ${BLUE}Create backup:${NC}     sudo $(readlink -f "$0") --backup-only"
    echo
    echo -e "${YELLOW}Bot deployed at:${NC}    ${DEPLOY_DIR}"
    echo -e "${YELLOW}Python venv at:${NC}     ${VENV_DIR}"
    echo -e "${YELLOW}Backups stored at:${NC}  ${BACKUP_DIR}"
    echo -e "${GREEN}=========================================================${NC}"
}

# Function to perform new installation
perform_installation() {
    log "INFO" "Performing fresh installation"
    
    # Create directories
    create_directories
    
    # Install dependencies
    install_dependencies || {
        log "ERROR" "Failed to install dependencies"
        exit 1
    }
    
    # Check if we need to clone from Git
    if [[ -n "$GITHUB_REPO" ]]; then
        log "INFO" "Cloning from GitHub repository: $GITHUB_REPO"
        git clone --depth 1 --branch "$GITHUB_BRANCH" "$GITHUB_REPO" "$DEPLOY_DIR" || {
            log "ERROR" "Failed to clone repository"
            exit 1
        }
    else
        log "INFO" "Using local source code"
        # Copy local source code here if needed
    fi
    
    # Detect project name and main file
    detect_project_name
    detect_main_file || {
        log "ERROR" "Failed to detect main file"
        exit 1
    }
    
    # Setup virtual environment
    setup_venv || {
        log "ERROR" "Failed to setup virtual environment"
        exit 1
    }
    
    # Handle env file
    handle_env_file
    
    # Setup systemd service
    setup_systemd_service || {
        log "ERROR" "Failed to setup systemd service"
        exit 1
    }
    
    # Start the service
    log "INFO" "Starting ${PROJECT_NAME} service"
    systemctl start "${PROJECT_NAME}.service" || {
        log "ERROR" "Failed to start service"
        exit 1
    }
    
    log "INFO" "Installation completed successfully"
    
    # Check service status
    check_service_status
    
    # Display service management guide
    display_service_guide
}

# Function to perform update
perform_update() {
    log "INFO" "Performing update"
    
    # Create backup first
    create_backup
    
    # Stop the service
    log "INFO" "Stopping ${PROJECT_NAME} service"
    systemctl stop "${PROJECT_NAME}.service" || {
        log "WARNING" "Failed to stop service, it might not be running"
    }
    
    # Preserve important files
    local preserved_files_dir=$(preserve_files)
    
    # Update from Git if repository is specified
    if [[ -n "$GITHUB_REPO" ]]; then
        log "INFO" "Updating from GitHub repository"
        
        # If git directory exists, pull updates
        if [[ -d "${DEPLOY_DIR}/.git" ]]; then
            log "INFO" "Pulling updates from repository"
            (cd "$DEPLOY_DIR" && git pull) || {
                log "ERROR" "Failed to pull updates"
                restore_preserved_files "$preserved_files_dir"
                systemctl start "${PROJECT_NAME}.service" || true
                exit 1
            }
        else
            log "INFO" "No git repository found, cloning fresh copy"
            rm -rf "${DEPLOY_DIR}.old" 2>/dev/null || true
            mv "$DEPLOY_DIR" "${DEPLOY_DIR}.old"
            git clone --depth 1 --branch "$GITHUB_BRANCH" "$GITHUB_REPO" "$DEPLOY_DIR" || {
                log "ERROR" "Failed to clone repository"
                mv "${DEPLOY_DIR}.old" "$DEPLOY_DIR"
                restore_preserved_files "$preserved_files_dir"
                systemctl start "${PROJECT_NAME}.service" || true
                exit 1
            }
        fi
    else
        log "INFO" "No GitHub repository specified, updating from local source"
        # Code to update from local source would go here
    fi
    
    # Detect main file (might have changed)
    detect_main_file || {
        log "ERROR" "Failed to detect main file after update"
        restore_preserved_files "$preserved_files_dir"
        systemctl start "${PROJECT_NAME}.service" || true
        exit 1
    }
    
    # Restore preserved files
    restore_preserved_files "$preserved_files_dir"
    
    # Update virtual environment
    log "INFO" "Updating virtual environment"
    setup_venv || {
        log "ERROR" "Failed to update virtual environment"
        systemctl start "${PROJECT_NAME}.service" || true
        exit 1
    }
    
    # Update systemd service (in case paths or main file changed)
    setup_systemd_service || {
        log "ERROR" "Failed to update systemd service"
        systemctl start "${PROJECT_NAME}.service" || true
        exit 1
    }
    
    # Start the service
    log "INFO" "Starting ${PROJECT_NAME} service"
    systemctl start "${PROJECT_NAME}.service" || {
        log "ERROR" "Failed to start service after update"
        exit 1
    }
    
    log "INFO" "Update completed successfully"
    
    # Check service status
    check_service_status
    
    # Display service management guide
    display_service_guide
    
    # Rotate backups
    rotate_backups
}

# =============================================================================
# Main Script
# =============================================================================

# Parse command line arguments
parse_args "$@"

# Check if running as root
check_root

# Initialize log file
echo "===== Telegram Bot Deployment Log - $(date) =====" > "$LOG_FILE"

# Display script header
echo -e "${BLUE}=======================================================${NC}"
echo -e "${BLUE}           Telegram Bot Deployment Script             ${NC}"
echo -e "${BLUE}=======================================================${NC}"
echo

# Check for debug mode
if [[ "$DEBUG" == true ]]; then
    log "DEBUG" "Debug mode enabled"
    set -x
fi

# Process based on mode
if [[ "$BACKUP_ONLY" == true ]]; then
    # Just create a backup
    log "INFO" "Running in backup-only mode"
    detect_project_name
    create_backup
    rotate_backups
    log "INFO" "Backup completed"
    exit 0
elif [[ -n "$ROLLBACK_VERSION" ]]; then
    # Perform rollback
    log "INFO" "Running in rollback mode"
    perform_rollback "$ROLLBACK_VERSION"
    exit $?
else
    # Check if we're installing or updating
    if detect_installation; then
        # Update existing installation
        perform_update
    else
        # Fresh installation
        perform_installation
    fi
fi

# Final log message
log "INFO" "Script completed successfully"

# Exit with success
exit 0
