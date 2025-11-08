# Contributing to RIPTIDAL

Thank you for your interest in contributing to RIPTIDAL! This document provides guidelines for contributing to this project.

## ⚠️ Ethical Guidelines

Before contributing, please understand and agree to these ethical principles:

### Code of Conduct

1. **Respect Copyright Laws**: All contributions must respect copyright and intellectual property rights
2. **Personal Use Focus**: This tool is designed for personal, educational use only
3. **No Piracy Enablement**: Do not contribute features that facilitate piracy or copyright infringement
4. **Legal Compliance**: Ensure your contributions comply with Tidal's Terms of Service and applicable laws

### Prohibited Contributions

We will **NOT** accept contributions that:
- Enable mass downloading for distribution purposes
- Circumvent DRM or copy protection mechanisms beyond personal use
- Facilitate sharing or selling of downloaded content
- Violate Tidal's Terms of Service
- Enable commercial use of downloaded content
- Remove or bypass authentication requirements

### Encouraged Contributions

We welcome contributions that:
- Improve code quality, performance, and reliability
- Enhance user experience and interface
- Add better error handling and logging
- Improve documentation
- Fix bugs and security issues
- Add features for personal library management
- Improve testing and code coverage

## How to Contribute

### Reporting Issues

1. Check if the issue already exists
2. Provide detailed information:
   - Python version
   - Operating system
   - Steps to reproduce
   - Expected vs actual behavior
   - Error messages and logs (remove personal information)

### Submitting Pull Requests

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes**:
   - Follow the existing code style
   - Add tests for new features
   - Update documentation as needed
   - Ensure all tests pass
4. **Commit your changes**: Use clear, descriptive commit messages
5. **Push to your fork**: `git push origin feature/your-feature-name`
6. **Submit a pull request**: Provide a clear description of your changes

### Code Standards

- **Python 3.12+**: Use modern Python features
- **Type Hints**: Add type hints to all functions
- **Documentation**: Document all public APIs with docstrings
- **Testing**: Write tests for new features
- **Code Style**: Follow PEP 8 and use Black for formatting
- **Async/Await**: Use async patterns for I/O operations

### Testing

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=. --cov-report=html

# Type checking
mypy .

# Code formatting
black .
isort .
```

## Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/riptidal.git
cd riptidal

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## Project Structure

```
riptidal/
├── api/              # Tidal API client
├── core/             # Core functionality
├── ui/               # User interface
├── utils/            # Utility functions
├── tests/            # Test suite
├── README.md         # Project documentation
├── CONTRIBUTING.md   # This file
├── LICENSE           # MIT License
└── pyproject.toml    # Project configuration
```

## Legal Considerations

By contributing to this project, you:
1. Agree that your contributions will be licensed under the MIT License
2. Confirm that you have the right to submit the contribution
3. Understand that this tool is for personal use only
4. Acknowledge the ethical guidelines outlined above
5. Will not hold the project maintainers liable for any misuse

## Questions?

If you have questions about contributing, please:
1. Check existing issues and discussions
2. Review the README and documentation
3. Open a new issue with the "question" label

## Recognition

Contributors will be recognized in the project's acknowledgements. Thank you for helping make RIPTIDAL better while respecting ethical and legal boundaries!

---

**Remember**: This project exists to help users manage their personal music libraries, not to facilitate piracy. Let's keep it that way.
