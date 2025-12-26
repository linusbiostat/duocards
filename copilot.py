# https://github.com/sst/models.dev/blob/dev/providers/github-copilot/models/gpt-4.1.toml
# https://raw.githubusercontent.com/sst/opencode-copilot-auth/refs/heads/main/index.mjs


import requests
import json
import time
import base64
from pathlib import Path
import os


class CopilotClient:
    CLIENT_ID = "Iv1.b507a08c87ecfe98"
    HEADERS = {
        "User-Agent": "GitHubCopilotChat/0.32.4",
        "Editor-Version": "vscode/1.105.1",
        "Editor-Plugin-Version": "copilot-chat/0.32.4",
        "Copilot-Integration-Id": "vscode-chat",
    }

    def __init__(self, enterprise_url=None, env_file=".env"):
        self.enterprise_url = enterprise_url
        self.domain = (
            self._normalize_domain(enterprise_url) if enterprise_url else "github.com"
        )
        self.access_token = None
        self.refresh_token = None
        self.token_expires = 0
        self.env_file = env_file

        # Set URLs
        if enterprise_url:
            self.base_url = f"https://copilot-api.{self.domain}"
        else:
            self.base_url = "https://api.githubcopilot.com"

        self.device_code_url = f"https://{self.domain}/login/device/code"
        self.access_token_url = f"https://{self.domain}/login/oauth/access_token"
        self.copilot_api_key_url = (
            f"https://api.{self.domain}/copilot_internal/v2/token"
        )

        # Try to load tokens from .env file
        self._load_tokens_from_env()

    def _file_to_base64(self, file_path):
        """Convert file to base64 string (raw data, no prefix)"""
        path = Path(file_path)
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _normalize_domain(self, url):
        if not url:
            return "github.com"
        return url.replace("https://", "").replace("http://", "").rstrip("/")

    def _load_tokens_from_env(self):
        """Load tokens from .env file"""
        with open(self.env_file, 'r') as f:
            for line in f:
                if line.startswith('access_token='):
                    self.access_token = line.split('=')[1].strip()
                elif line.startswith('refresh_token='):
                    self.refresh_token = line.split('=')[1].strip()
        print("✓ tokens loaded from .env file")
        # set expiry to 0 to force refresh on first use
        self.token_expires = 0
        return True


    def _save_tokens_to_env(self):
        """Save tokens to .env file"""
        env_content = f'access_token="{self.access_token}"\nrefresh_token="{self.refresh_token}"\n'
        with open(self.env_file, "w") as f:
            f.write(env_content)
        print(f"✓ Tokens saved to {self.env_file}")

    def authenticate(self):
        """Start device flow authentication"""
        response = requests.post(
            self.device_code_url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "GitHubCopilotChat/0.35.0",
            },
            json={
                "client_id": self.CLIENT_ID,
                "scope": "read:user",
            },
        )

        if not response.ok:
            raise Exception("Failed to initiate device authorization")

        device_data = response.json()

        print(f"\nPlease visit: {device_data['verification_uri']}")
        print(f"Enter code: {device_data['user_code']}\n")

        # Poll for token
        while True:
            time.sleep(device_data["interval"])

            token_response = requests.post(
                self.access_token_url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "GitHubCopilotChat/0.35.0",
                },
                json={
                    "client_id": self.CLIENT_ID,
                    "device_code": device_data["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )

            if not token_response.ok:
                continue

            data = token_response.json()

            if "access_token" in data:
                self.refresh_token = data["access_token"]
                print("✓ Authentication successful!\n")
                self._refresh_copilot_token()
                self._save_tokens_to_env()
                return True

            if data.get("error") == "authorization_pending":
                continue

            if "error" in data:
                raise Exception(f"Authentication failed: {data['error']}")

    def _refresh_copilot_token(self):
        """Get Copilot API token"""
        if not self.refresh_token:
            raise Exception("No refresh token available. Please authenticate first.")

        response = requests.get(
            self.copilot_api_key_url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.refresh_token}",
                **self.HEADERS,
            },
        )

        if not response.ok:
            raise Exception(
                f"Failed to get Copilot token: {response.status_code} - {response.text}"
            )

        token_data = response.json()
        self.access_token = token_data["token"]
        self.token_expires = token_data["expires_at"] * 1000

        # Update .env file with new access token
        self._save_tokens_to_env()

    def _ensure_token_valid(self):
        """Refresh token if expired"""
        if not self.access_token or self.token_expires < time.time() * 1000:
            self._refresh_copilot_token()

    def _image_to_base64(self, image_path):
        """Convert image to base64 data URL"""
        path = Path(image_path)
        with open(path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Determine mime type
        ext = path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(ext, "image/png")

        return f"data:{mime_type};base64,{image_data}"

    def chat(
        self,
        message=None,
        messages=None,
        images=None,
        model="gpt-4.1",
        stream=False,
        tools=None,
        tool_choice=None,
    ):
        """
        Send a chat message with optional images, tools, and message history.
        Based on copilotapi.mjs, sets X-Initiator to 'agent' if tools or assistant roles are present.
        """
        self._ensure_token_valid()

        if messages is None:
            if message is None:
                raise ValueError("Must provide 'message' or 'messages'")

            # Build content list
            content = []

            # 1. Add Text
            if message:
                content.append({"type": "text", "text": message})

            # 2. Add Images
            if images:
                for image_path in images:
                    # Note: Images use "image_url" with a data URI prefix
                    data_uri = (
                        f"data:image/jpeg;base64,{self._file_to_base64(image_path)}"
                    )
                    content.append(
                        {"type": "image_url", "image_url": {"url": data_uri}}
                    )

            messages = [{"role": "user", "content": content}]

        # --- Determine Headers based on message content ---

        # Check if this is an "agent" call (tool use) based on copilotapi.mjs logic
        is_agent_call = any(
            msg.get("role") in ["tool", "assistant"] for msg in messages
        )
        initiator = "agent" if is_agent_call else "user"

        # Check if any message in the history contains an image
        is_vision_request = any(
            isinstance(msg.get("content"), list)
            and any(part.get("type") == "image_url" for part in msg["content"])
            for msg in messages
        )

        headers = {
            **self.HEADERS,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Openai-Intent": "conversation-edits",
            "X-Initiator": initiator,  # <-- Set based on mjs logic
        }

        if is_vision_request:
            headers["Copilot-Vision-Request"] = "true"

        # --- Build Payload ---
        payload = {
            "messages": messages,
            "model": model,
            "stream": stream,
            "temperature": 0.1,
            "top_p": 1,
            "n": 1,
        }

        # Add tools if provided (OpenAI compatible)
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            stream=stream,
        )

        if not response.ok:
            raise Exception(
                f"API request failed: {response.status_code} - {response.text}"
            )

        if stream:
            return self._handle_stream(response)
        else:
            result = response.json()
            # Return the full message object, which may contain 'content' or 'tool_calls'
            return result["choices"][0]["message"]

    def _handle_stream(self, response):
        """
        Handle streaming response, now supports assembling tool calls.
        """
        full_message_obj = {"role": "assistant", "content": ""}
        tool_calls = []

        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            delta = chunk["choices"][0].get("delta", {})

                            # Handle content delta
                            if "content" in delta and delta["content"]:
                                content = delta["content"]
                                print(content, end="", flush=True)
                                full_message_obj["content"] += content

                            # Handle tool_calls delta
                            if "tool_calls" in delta:
                                for tc_delta in delta["tool_calls"]:
                                    index = tc_delta["index"]

                                    # Ensure the tool_calls list is long enough
                                    if len(tool_calls) <= index:
                                        tool_calls.append(
                                            {
                                                "id": "",
                                                "type": "function",
                                                "function": {
                                                    "name": "",
                                                    "arguments": "",
                                                },
                                            }
                                        )

                                    # Append deltas
                                    if tc_delta.get("id"):
                                        tool_calls[index]["id"] = tc_delta["id"]
                                    if tc_delta.get("type"):
                                        tool_calls[index]["type"] = tc_delta["type"]

                                    if "function" in tc_delta:
                                        if tc_delta["function"].get("name"):
                                            tool_calls[index]["function"]["name"] = (
                                                tc_delta["function"]["name"]
                                            )
                                        if tc_delta["function"].get("arguments"):
                                            tool_calls[index]["function"][
                                                "arguments"
                                            ] += tc_delta["function"]["arguments"]

                    except json.JSONDecodeError:
                        print(f"Failed to decode JSON chunk: {data}")
                        pass

        print()  # New line after streaming

        if tool_calls:
            full_message_obj["tool_calls"] = tool_calls

        # Clean up empty content key if only tools were called
        if not full_message_obj["content"]:
            del full_message_obj["content"]

        return full_message_obj


# --- Mock Tool Functions ---
def get_current_weather(location, unit="celsius"):
    """Get the current weather in a given location"""
    if "tokyo" in location.lower():
        return json.dumps({"location": "Tokyo", "temperature": "15", "unit": unit})
    elif "san francisco" in location.lower():
        return json.dumps(
            {"location": "San Francisco", "temperature": "18", "unit": unit}
        )
    else:
        return json.dumps({"location": location, "temperature": "22", "unit": unit})


def get_stock_price(ticker):
    """Get the current stock price for a given ticker symbol"""
    if ticker.lower() == "msft":
        return json.dumps({"ticker": "MSFT", "price": "430.50"})
    elif ticker.lower() == "goog":
        return json.dumps({"ticker": "GOOG", "price": "175.20"})
    else:
        return json.dumps({"ticker": ticker, "price": "100.00"})


# Example usage
if __name__ == "__main__":
    # Initialize client (will automatically load tokens from .env)
    client = CopilotClient()

    # Only authenticate if tokens aren't available
    if not client.refresh_token:
        print("No tokens found in .env file. Starting authentication...")
        client.authenticate()

    # # --- Basic Text Prompt (Old Example) ---
    # print("Which model are you?")
    # # Note: .chat() now returns a message object
    # response_msg = client.chat("Which model are you?")
    # print(response_msg.get("content", "[No content received]"))
    # print("\n" + "=" * 50 + "\n")

    # --- NEW: Tool Call Example ---
    # print("Starting tool call example...")
    #
    # # 1. Define the tools the model can use
    # tools = [
    #     {
    #         "type": "function",
    #         "function": {
    #             "name": "get_current_weather",
    #             "description": "Get the current weather in a given location",
    #             "parameters": {
    #                 "type": "object",
    #                 "properties": {
    #                     "location": {
    #                         "type": "string",
    #                         "description": "The city and state, e.g., San Francisco, CA",
    #                     },
    #                     "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
    #                 },
    #                 "required": ["location"],
    #             },
    #         },
    #     },
    #     {
    #         "type": "function",
    #         "function": {
    #             "name": "get_stock_price",
    #             "description": "Get the current stock price for a given ticker symbol",
    #             "parameters": {
    #                 "type": "object",
    #                 "properties": {
    #                     "ticker": {
    #                         "type": "string",
    #                         "description": "The stock ticker symbol, e.g., MSFT",
    #                     },
    #                 },
    #                 "required": ["ticker"],
    #             },
    #         },
    #     },
    # ]
    #
    # # Define our available functions
    # available_functions = {
    #     "get_current_weather": get_current_weather,
    #     "get_stock_price": get_stock_price,
    # }
    #
    # # 2. Start the conversation
    # messages = [
    #     {
    #         "role": "user",
    #         "content": "What's the weather in San Francisco and what's the stock price for MSFT?",
    #     }
    # ]
    # print(f"User: {messages[0]['content']}")
    #
    # # 3. Send the first message with tools
    # # We use stream=False here for a cleaner step-by-step demo
    # assistant_message = client.chat(
    #     messages=messages,
    #     model="gpt-4.1",
    #     tools=tools,
    #     tool_choice="auto",
    #     stream=False,
    # )
    #
    # # 4. Add the assistant's response (which should contain tool_calls) to history
    # messages.append(assistant_message)
    #
    # # 5. Check if the model wants to call tools
    # if assistant_message.get("tool_calls"):
    #     print("\nAssistant wants to call tools:")
    #     print(json.dumps(assistant_message["tool_calls"], indent=2))
    #
    #     # 6. Execute each tool call
    #     for tool_call in assistant_message["tool_calls"]:
    #         function_name = tool_call["function"]["name"]
    #         function_to_call = available_functions.get(function_name)
    #
    #         if function_to_call:
    #             function_args = json.loads(tool_call["function"]["arguments"])
    #             print(f"Calling: {function_name}({function_args})")
    #
    #             # Call the function
    #             function_response = function_to_call(**function_args)
    #
    #             # 7. Add the tool's response to the message history
    #             messages.append(
    #                 {
    #                     "tool_call_id": tool_call["id"],
    #                     "role": "tool",
    #                     "name": function_name,
    #                     "content": function_response,
    #                 }
    #             )
    #         else:
    #             print(f"Error: Unknown function '{function_name}'")
    #
    #     # 8. Send the *entire* message history back to the model
    #     print("\nSending tool results back to model...")
    #     final_response_message = client.chat(
    #         messages=messages, model="gpt-4.1", tools=tools
    #     )
    #
    #     print(f"\nFinal Assistant Response:\n{final_response_message.get('content')}")
    #     messages.append(final_response_message)
    #
    # else:
    #     # The model responded without calling tools
    #     print(f"\nAssistant (no tools):\n{assistant_message.get('content')}")
    #
    # print("\n" + "=" * 50 + "\n")
    # print("Full Conversation History:")
    # print(json.dumps(messages, indent=2))
    # print("\n" + "=" * 50 + "\n")
    #

    PAGEPROMPT = """Analyze this supermarket flyer and extract ALL products, promotions, and sales.

    Include:
    - Individual products with prices
    - Category-wide sales
    - Special promotions ("Aktionen")

    Return empty array if no items found. Don't report items that do not have a percentage sale or reduced price, or are expected offers next week.
    Use the following schema and response format: "response_mime_type": "application/json", "response_json_schema": FlyerData.model_json_schema()


    class ProductItem(BaseModel):
        # Single product or promotion from a flyer.
        
        brand_name: Optional[str] = Field(
            None,  # Explicit default
            description="Brand name"
        )
        
        product_name: str = Field(
            ...,  # Explicit required field
            description="Product name or promotion description"
        )
        
        current_price: Optional[float] = Field(
            None,
            ge=0,  # Must be >= 0 if provided
            description="Discounted/current price"
        )
        
        original_price: Optional[float] = Field(
            None,
            ge=0,
            description="Original price before discount"
        )
        
        unit: Optional[str] = Field(
            None,
            description="Unit of measurement (e.g., 'per 200g', 'Stück')"
        )
        
        percentage_sale: Optional[int] = Field(
            None,
            ge=0,
            le=100,  # Percentage validation
            description="Discount percentage (0-100)"
        )

    class FlyerData(BaseModel):
        # Complete flyer extraction result.
        
        items: List[ProductItem] = Field(
            default_factory=list,  # Better than mutable default
            description="All products and promotions from the flyer"
        )
    """

    # --- Image Example (commented out) ---
    # TMPIMAGEPATH = "/tmp/tmppage.png"
    # pdfname = "/tmp/aldi.pdf"
    # print("Image example:")
    # with pymupdf.open(pdfname) as pdf:
    #     for i, page in enumerate(pdf):
    #         try:
    #             page.get_pixmap().save(TMPIMAGEPATH)
    #             response_msg = client.chat(PAGEPROMPT, images=[TMPIMAGEPATH])
    #             print(response_msg.get("content"))
    #             print("\n" + "=" * 50 + "\n")
    #         except Exception as e:
    #             print(f"Error processing page {i} of {pdfname}: {e}")

    # --- Streaming Example (commented out) ---
    # print("Streaming example (with tools):")
    # messages = [{"role": "user", "content": "What's the weather in Tokyo?"}]
    # stream_response_msg = client.chat(messages=messages, tools=tools, stream=True)
    # print("\n--- Full streamed message object ---")
    # print(json.dumps(stream_response_msg, indent=2))
