.PHONY: test build clean all

# Run the full test suite
test:
	uv run python -m unittest discover tests

# Build the source distribution and wheel
build:
	uv build

# Clean up build artifacts and cache directories
clean:
	rm -rf dist/ build/ *.egg-info .venv/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Run clean, then test, then build
all: clean test build
