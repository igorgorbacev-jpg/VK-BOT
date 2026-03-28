# Context: Phase 1 — Environment & Authentication

## Phase Goal
Establish secure connections to VK APIs, implement class-based bot structure, and verify both Group and User token capabilities.

## Decisions

### 1. Token Management & Configuration
- **Names**: `VK_USER_TOKEN`, `VK_GROUP_TOKEN`, `VK_GROUP_ID`.
- **Library**: `python-dotenv` for loading environment variables.
- **Setup**: `.env` file in the project root; provide `.env.example` as a template.
- **Validation**: Bot must "fail fast" if tokens are missing or invalid on startup.

### 2. Bot Entry Point & Structure
- **Architecture**: Class-based implementation using `class VKinderBot`.
- **Modularity**: VK API interaction logic must be separated into `vk_client.py`.
- **Entry Point**: `main.py` will serve as the primary execution script.
- **Event Loop**: Use `vk_api.longpoll` for handling incoming group messages.

### 3. Basic Greeting & Help Message
- **Trigger**: Keywords `start`, `hello` (case-insensitive).
- **Greeting**: "Привет, [Имя]! Я VKinder. Напиши 'next' для поиска."
- **Help**: Separate command `/help` to provide usage instructions.
- **Personalization**: Always fetch and use the user's first name in the greeting.

### 4. Initial VK Search Verification
- **Standalone Check**: Create `check_auth.py` to verify User Token search capabilities independently.
- **Debug Command**: Implement a temporary `/test_search` command in the bot to confirm search results in real-time.
- **Verification Output**: Must confirm success with "User search API: OK (N results)".

## Code Context
- **Dependencies**: `vk_api`, `python-dotenv`.
- **Files to Create**:
  - `main.py` (Bot entry point)
  - `vk_client.py` (API wrapper)
  - `check_auth.py` (Verification script)
  - `.env.example` (Configuration template)

## Deferred Ideas
*(None for this phase)*
