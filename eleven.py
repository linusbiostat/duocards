import json
import base64
import threading
from botasaurus_driver import Driver, cdp
from botasaurus_driver.exceptions import ChromeException
from typing import Optional


# --- Helper Class: CustomResponse ---
class CustomResponse:
    """
    A custom Response class to correctly parse a stream of
    concatenated JSON objects.
    """

    def __init__(self, request_id, content, is_base_64):
        self.request_id = request_id
        self.content = content
        self.is_base_64 = is_base_64

    def get_decoded_content(self):
        """Decodes the content if it's Base64 encoded."""
        if self.is_base_64 and self.content:
            try:
                decoded_bytes = base64.b64decode(self.content)
                return decoded_bytes.decode("utf-8")
            except Exception as e:
                print(f"Warning: Could not decode base64 content: {e}")
                return None
        return self.content

    def get_json_content(self):
        """
        Parses a stream of concatenated or newline-delimited
        JSON objects from the content.
        """
        decoded_content = self.get_decoded_content()
        if not decoded_content:
            return []

        json_objects = []
        decoder = json.JSONDecoder()
        content = decoded_content.strip()
        pos = 0

        while pos < len(content):
            try:
                # Skip whitespace
                while pos < len(content) and content[pos].isspace():
                    pos += 1

                if pos == len(content):
                    break  # End of string

                # Use raw_decode to parse one JSON object
                obj, end_pos = decoder.raw_decode(content[pos:])
                json_objects.append(obj)
                pos += end_pos

            except json.JSONDecodeError as e:
                print(f"Warning: JSON decode error at position {pos}: {e}")
                print(f"Stopping parse at data: {content[pos : pos + 200]}...")
                break  # Stop parsing

        return json_objects


# --- Helper Function: safe_collect_response ---
# (This function is correct, no changes needed)
def safe_collect_response(driver_instance, request_id):
    """
    Safely fetches the response body for a request_id,
    bypassing bugs in the driver's default collector.
    """
    try:
        body, base64Encoded = driver_instance.run_cdp_command(
            cdp.network.get_response_body(request_id)
        )
        return CustomResponse(
            request_id=request_id,
            content=body,
            is_base_64=base64Encoded,
        )
    except ChromeException as e:
        print(
            f"Warning: Could not get response body for {request_id}. Error: {e.message}"
        )
        return CustomResponse(
            request_id=request_id,
            content=None,
            is_base_64=False,
        )


# --- Main Function: generate_audio ---


def generate_audio(driver, text, output_filename: str = "audio.mp3") -> Optional[str]:
    """
    Launches a browser, navigates to ElevenLabs, and waits for the user
    to generate an audio file. It then captures the network response
    and saves the concatenated audio to the specified output file.

    :param output_filename: The name of the file to save the audio as (e.g., "my_audio.mp3")
    :return: True if audio was successfully saved, False otherwise.
    """
    print(f"Starting audio generation. Output will be saved to {output_filename}")

    audios = []  # This list will hold all the 'audio_base64' strings

# --- Helper Function: setup_handlers ---
def setup_handlers(driver):
    """
    Sets up the event handlers on the driver ONLY ONCE.
    It uses a context object attached to the driver to coordinate
    state between the handlers and the main function.
    """
    if hasattr(driver, "_eleven_handlers_registered") and driver._eleven_handlers_registered:
        return  # Handlers already registered

    # 1. Define handlers that read from the driver's context
    def before_request_handler(
        request_id: str,
        request: cdp.network.Request,
        event: cdp.network.RequestWillBeSent,
    ):
        """
        This function is called *before* every network request is sent.
        """
        # Ensure context exists
        if not hasattr(driver, "_eleven_context"):
            return

        ctx = driver._eleven_context
        # If we already found a target, we might skip, or just keep looking (depending on logic).
        # Here we mimic original logic: find target POST request.
        
        url = request.url
        method = request.method

        if "api.elevenlabs.io/v1" in url and "stream" in url and method == "POST":
            print(f"Handler found target POST request: {url}")
            # Save request_id to context
            if not ctx.get("target_request_id"):
                ctx["target_request_id"] = request_id

    def loading_finished_handler(event: cdp.network.LoadingFinished):
        """
        This function is called when *any* network request finishes.
        """
        if not hasattr(driver, "_eleven_context"):
            return

        ctx = driver._eleven_context
        request_id = event.request_id
        
        target_id = ctx.get("target_request_id")

        if target_id and request_id == target_id:
            print(f"Target request {request_id} finished.")
            # Signal completion
            if "finished_event" in ctx:
                ctx["finished_event"].set()

    # 2. Register the handlers
    driver.before_request_sent(before_request_handler)
    driver._tab.add_handler(cdp.network.LoadingFinished, loading_finished_handler)
    
    # 3. Mark as registered
    driver._eleven_handlers_registered = True
    print("One-time event handlers registered on driver.")


# --- Main Function: generate_audio ---


def generate_audio(driver, text, output_filename: str = "audio.mp3") -> Optional[str]:
    """
    Launches a browser, navigates to ElevenLabs, and waits for the user
    to generate an audio file. It then captures the network response
    and saves the concatenated audio to the specified output file.

    :param output_filename: The name of the file to save the audio as (e.g., "my_audio.mp3")
    :return: True if audio was successfully saved, False otherwise.
    """
    print(f"Starting audio generation. Output will be saved to {output_filename}")

    audios = []  # This list will hold all the 'audio_base64' strings

    # Initialize the context for THIS run
    driver._eleven_context = {
        "target_request_id": None,
        "finished_event": threading.Event()
    }
    
    # Ensure handlers are set up (idempotent)
    setup_handlers(driver)

    try:
        # 3. Manually enable network buffering (idempotent-ish, but safe to call)
        # We can check if we already enabled it to avoid spamming logs, but usually harmless.
        if not getattr(driver, "_eleven_network_enabled", False):
            print("Enabling network domain with buffering...")
            driver.run_cdp_command(
                cdp.network.enable(
                    max_total_buffer_size=1024 * 1024 * 400,  # 400 MB
                    max_resource_buffer_size=1024 * 1024 * 200,  # 200 MB
                )
            )
            # 4. Manually add cdp.network to the list of enabled domains
            if cdp.network not in driver._tab.enabled_domains:
                driver._tab.enabled_domains.append(cdp.network)
            driver._eleven_network_enabled = True

        # 5. Navigate to the page
        print("Clearing browser cache and cookies...")
        try:
            driver.run_cdp_command(cdp.network.clear_browser_cookies())
            driver.run_cdp_command(cdp.network.clear_browser_cache())
            driver.sleep(0.5)
        except Exception as e:
            print(f"Warning: Could not clear cache/cookies: {e}")

        print("Navigating to https://elevenlabs.io/de/text-to-speech ...")
        driver.get("https://elevenlabs.io/de/text-to-speech/slovenian")
        driver.enable_human_mode()

        acbutton = driver.select(".cb-btn-accept")
        if acbutton:
            acbutton.click()
        textinput = driver.select("div[placeholder]", wait=20)
        driver.sleep(1)
        textinput.run_js("(el) => el.innerHTML = ''")
        textinput.focus()
        textinput.run_js(f"(el) => document.execCommand('insertText', false, `{text}`)")
        driver.sleep(1)
        driver.get_element_with_exact_text("Play").click()

        # 6. Wait for the stream to finish using the event from context
        print("Waiting for audio stream to finish...")
        finished_event = driver._eleven_context["finished_event"]
        finished_in_time = finished_event.wait(timeout=60.0)

        if not finished_in_time:
            print(
                "Warning: Timed out waiting for audio stream. The file might be incomplete."
            )
        else:
            print("Audio stream finished.")

        # 7. Process the response in the main thread
        target_request_id = driver._eleven_context.get("target_request_id")
        
        if target_request_id:
            print(f"Collecting response for request ID: {target_request_id}")
            response = safe_collect_response(driver, target_request_id)

            if response.content:
                response_data_list = response.get_json_content()
                if response_data_list:
                    print(
                        f"Found {len(response_data_list)} JSON objects in the stream."
                    )
                    for data_obj in response_data_list:
                        if isinstance(data_obj, dict) and "audio_base64" in data_obj:
                            audios.append(data_obj["audio_base64"])
                else:
                    print("Content found, but no valid JSON objects could be parsed.")
            else:
                print(f"(No Content for request {target_request_id})")
        else:
            print(
                "Stream finished (or timed out) but no target request ID was captured."
            )

        # 8. Decode and save the audio
        print(f"\\nSuccessfully extracted {len(audios)} audio base64 strings.")

        if audios:
            print("\\nDecoding and concatenating audio data...")
            decoded_audio_data = []
            for i, b64_string in enumerate(audios):
                try:
                    audio_bytes = base64.b64decode(b64_string)
                    decoded_audio_data.append(audio_bytes)
                except Exception:
                    print(
                        f"Error: Could not decode base64 string at index {i}. Skipping."
                    )

            if decoded_audio_data:
                final_audio = b"".join(decoded_audio_data)
                completebase64 = base64.b64encode(final_audio).decode("utf-8")

                with open(output_filename, "wb") as f:
                    f.write(final_audio)

                print(f"Successfully saved concatenated audio to '{output_filename}'")
                return completebase64  # Success!
            else:
                print("No valid audio data was decoded.")
                return None  # Failed to decode
        else:
            print("No audio data was found in the network responses.")
            return None  # Failed to find audio

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None  # Failed due to exception


# --- Example Usage ---
# This block will only run if the script is executed directly
if __name__ == "__main__":
    driver = Driver()
    text = """
Ptič iz lesa

Poden pod Triglavom, kjer se jesenski veter igra z rdečimi listi bukve, je stal lesen hišica s počrnelo streho. V njej je živel Stane, osemdesetletni možakar, ki je poznal vsak kamen v teh hribih. Njegove roke, zgrbljene in močne, so bile zadnje v vasi, ki še obvladajo staro umetnost rezbarjenja.

Vsako jesen je na njegov prag stopila Maja, sosedova vnukinja, s košaro s potico in radovednimi očmi. "Stari Stane," je rekla letos, ko je zaprla za seboj lesena vrata, "ali mi boš pokazal, kako narediti ptiča?"

Mož je pokimal, kot bi čakal samo na to vprašanje. Vzel je kos lipovega lesa in ga položil na mizo. "Ptiča ne narediš, Majčica. Ptiča najdeš. On je v lesu. Ti samo odstraniš, kar ni ptič."

Maja je strmela v kos lesa. Videla je samo deblo. Stane je vzel dleti in začel počasi, z dihom narave, odstranjevati ostre robove. "Vidiš," je šepetal, "tukaj je krilo. Tukaj pa kljun. Les ti pove, če poslušaš."

        """

    # Call the function and save the output
    success = generate_audio(driver, text, output_filename="audio.mp3")

    if success:
        print("Audio generation complete.")
    else:
        print("Audio generation failed.")
    # Call the function and save the output
    success = generate_audio(driver, "Danes sije sonce.", output_filename="audio.mp3")

    if success:
        print("Audio generation complete.")
    else:
        print("Audio generation failed.")

