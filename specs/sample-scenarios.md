# Scenarios: Greeting Function

## Scenario 1: Basic greeting
Given: A name "Alice"
When: greet("Alice") is called
Then: Returns "Hello, Alice!"
Validation: Test asserts return value equals "Hello, Alice!"

## Scenario 2: Empty name
Given: An empty string ""
When: greet("") is called
Then: Returns "Hello, World!"
Validation: Test asserts return value equals "Hello, World!"

## Scenario 3: Whitespace handling
Given: A name "  Bob  "
When: greet("  Bob  ") is called
Then: Returns "Hello, Bob!"
Validation: Test asserts return value equals "Hello, Bob!"
