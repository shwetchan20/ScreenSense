"""Demo Mode Responses

Hardcoded responses for demo purposes. Bypasses entire inference pipeline.
Triggered by keywords in window title or clipboard content.
"""

from __future__ import annotations

# Trigger keywords mapped to ARIA responses
# Format: keyword (case-insensitive) -> response text
DEMO_RESPONSES: dict[str, str] = {
    # Browser/Web
    "stack overflow": "I see you're on Stack Overflow. Looking for solutions to a coding problem? I can help explain any code snippets you find.",
    "stackoverflow": "I see you're on Stack Overflow. Looking for solutions to a coding problem? I can help explain any code snippets you find.",
    "github": "You're browsing GitHub. Need help understanding this repository structure or want me to explain any code?",
    "youtube": "Watching a tutorial on YouTube? Let me know if you need me to take notes or summarize key points.",
    "google": "Searching on Google. What are you trying to find? I can help refine your search or explain results.",
    "documentation": "Reading documentation. I can help clarify any confusing sections or provide examples.",
    "reddit": "Browsing Reddit. Found something interesting? I can help analyze or summarize the discussion.",
    
    # Development
    "visual studio code": "VS Code is open. I'm monitoring for errors and can help with code suggestions when you need them.",
    "vscode": "VS Code is open. I'm monitoring for errors and can help with code suggestions when you need them.",
    "pycharm": "PyCharm detected. I'm watching for errors and ready to help debug when needed.",
    "error": "I notice an error on screen. Would you like me to analyze it and suggest a fix?",
    "exception": "There's an exception showing. I can help debug this - just let me know what you're trying to accomplish.",
    "traceback": "I see a traceback. This looks like a Python error. Want me to explain what went wrong and how to fix it?",
    "syntax error": "Syntax error detected. Usually a missing bracket, quote, or colon. Let me help you spot it.",
    "import error": "Import error - looks like a missing package. You probably need to install it with pip.",
    "undefined": "Undefined variable or function. Check your spelling or make sure it's defined before use.",
    
    # Terminal/Command Line
    "powershell": "PowerShell terminal active. Running commands? I can help with syntax or explain what commands do.",
    "command prompt": "Command prompt open. Need help with any commands or want to automate something?",
    "terminal": "Terminal detected. I'm here if you need command suggestions or want to understand output.",
    "npm": "Working with npm. Installing packages or running scripts? Let me know if you hit any issues.",
    "pip install": "Installing Python packages. I'll watch for any dependency conflicts or errors.",
    "git": "Git command detected. Need help with version control or resolving merge conflicts?",
    
    # Productivity
    "notion": "Notion is open. Taking notes or planning? I can help organize your thoughts.",
    "obsidian": "Obsidian detected. Building your knowledge base? I can suggest connections between notes.",
    "todo": "I see a TODO list. Want me to help prioritize or break down any complex tasks?",
    "calendar": "Calendar open. Planning your schedule? I can help estimate task durations.",
    "email": "Email client active. Need help drafting a response or summarizing a long thread?",
    
    # Learning
    "tutorial": "Following a tutorial? I can take notes for you or clarify any confusing steps.",
    "course": "Taking a course? I'm here to help explain concepts or answer questions as you learn.",
    "udemy": "Udemy course detected. Learning something new? I can help reinforce concepts with examples.",
    "coursera": "Coursera course open. Want me to summarize key points or create practice questions?",
    
    # Communication
    "slack": "Slack is active. I can help draft messages or summarize long conversation threads.",
    "discord": "Discord open. In a coding discussion? I can help explain technical concepts.",
    "teams": "Microsoft Teams detected. Need help preparing for a meeting or summarizing chat?",
    "zoom": "Zoom meeting active. I'll stay quiet during your call but I'm here if you need quick info.",
    
    # Design/Creative
    "figma": "Figma detected. Designing UI? I can suggest accessibility improvements or layout ideas.",
    "photoshop": "Photoshop open. Working on graphics? Let me know if you need technique suggestions.",
    "canva": "Canva active. Creating designs? I can help with color schemes or layout balance.",
    
    # Data/Analysis
    "jupyter": "Jupyter notebook open. Running data analysis? I can help explain results or suggest visualizations.",
    "excel": "Excel detected. Working with data? I can help with formulas or data cleaning strategies.",
    "pandas": "Using pandas. Data manipulation in progress? I can suggest efficient operations.",
    "matplotlib": "Creating visualizations with matplotlib. Want suggestions for better chart types or styling?",
    
    # Databases
    "sql": "SQL query detected. Need help optimizing the query or understanding the results?",
    "database": "Database work in progress. I can help with schema design or query optimization.",
    "mongodb": "MongoDB detected. Working with NoSQL? I can help with query syntax or data modeling.",
    
    # AI/ML
    "tensorflow": "TensorFlow detected. Training a model? I can help interpret metrics or suggest improvements.",
    "pytorch": "PyTorch in use. Building neural networks? Let me know if you need architecture suggestions.",
    "machine learning": "Machine learning work detected. I can help with model selection or hyperparameter tuning.",
    "neural network": "Neural network training. Want help understanding the architecture or debugging training issues?",
    
    # General coding
    "python": "Python code detected. I'm monitoring for errors and ready to help with any questions.",
    "javascript": "JavaScript code visible. Need help with async operations or debugging?",
    "typescript": "TypeScript detected. Type errors? I can help clarify type definitions.",
    "react": "React development in progress. Component issues? I can suggest patterns or optimizations.",
    "api": "API work detected. Need help with endpoints, authentication, or response handling?",
    "json": "Working with JSON data. Need help parsing or structuring the data?",
    
    # System/DevOps
    "docker": "Docker detected. Container issues? I can help with Dockerfile optimization or debugging.",
    "kubernetes": "Kubernetes work in progress. Need help with deployments or service configuration?",
    "aws": "AWS console open. Cloud infrastructure work? I can help with service selection or configuration.",
    "azure": "Azure portal detected. Need help with cloud resources or deployment?",
    
    # Testing
    "pytest": "Running pytest. Test failures? I can help debug or suggest better test cases.",
    "unittest": "Unit tests detected. Need help writing test cases or understanding failures?",
    "jest": "Jest testing in progress. Test failures? I can help fix them or improve coverage.",
    
    # Default fallback
    "code": "I see you're coding. I'm monitoring for errors and ready to help when you need me.",
    "programming": "Programming in progress. I'm here to help with any questions or debugging needs.",
}

# Special clipboard triggers (exact matches)
CLIPBOARD_TRIGGERS: dict[str, str] = {
    "help": "I'm ARIA, your desktop AI assistant. I monitor your screen for errors, provide coding help, and can explain concepts. Just ask!",
    "aria": "Yes? I'm here and monitoring your screen. What do you need help with?",
    "error": "I'm checking for errors on your screen. If you're seeing one, I can help debug it.",
}


def get_demo_response(window_title: str, clipboard_content: str | None = None) -> str | None:
    """
    Check if window title or clipboard contains trigger keywords.
    Returns hardcoded response if match found, None otherwise.
    
    Args:
        window_title: Active window title
        clipboard_content: Current clipboard text (optional)
    
    Returns:
        Demo response string if triggered, None otherwise
    """
    if not window_title:
        return None
    
    # Normalize for case-insensitive matching
    title_lower = window_title.lower()
    
    # Check window title triggers
    for keyword, response in DEMO_RESPONSES.items():
        if keyword in title_lower:
            return response
    
    # Check clipboard triggers (exact match)
    if clipboard_content:
        clipboard_lower = clipboard_content.strip().lower()
        if clipboard_lower in CLIPBOARD_TRIGGERS:
            return CLIPBOARD_TRIGGERS[clipboard_lower]
        
        # Also check partial matches in clipboard
        for keyword, response in DEMO_RESPONSES.items():
            if keyword in clipboard_lower:
                return response
    
    return None


def add_demo_response(keyword: str, response: str) -> None:
    """
    Add a new demo response at runtime.
    
    Args:
        keyword: Trigger keyword (case-insensitive)
        response: Response text to speak
    """
    DEMO_RESPONSES[keyword.lower()] = response


def remove_demo_response(keyword: str) -> bool:
    """
    Remove a demo response.
    
    Args:
        keyword: Trigger keyword to remove
    
    Returns:
        True if removed, False if not found
    """
    keyword_lower = keyword.lower()
    if keyword_lower in DEMO_RESPONSES:
        del DEMO_RESPONSES[keyword_lower]
        return True
    return False


def list_demo_triggers() -> list[str]:
    """
    Get list of all trigger keywords.
    
    Returns:
        List of trigger keywords
    """
    return sorted(DEMO_RESPONSES.keys())
