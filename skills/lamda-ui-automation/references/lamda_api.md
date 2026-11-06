# LAMDA 10.9 API Cheat Sheet

Source of truth: the installed `lamda` package, version `10.9`. Do not invent method names or selector fields.

## Connect

```python
from lamda.client import Device, Keys, Point, Corner, Direction

d = Device("127.0.0.1", 65000)
d = Device("127.0.0.1", 65000, certificate="/path/to/lamda.pem")
```

`Device(host, port=65000, certificate=None, session=None)`.

## Screen and device

```python
d.server_info()                  # .version, .architecture
d.device_info()
d.current_application()
d.is_screen_on() / d.is_screen_locked()
d.wake_up() / d.sleep()
d.screenshot(quality=90).save("screen.jpg")       # BytesIO
d.dump_window_hierarchy().getvalue()             # XML bytes
d.wait_for_idle(timeout)                          # milliseconds
```

## App lifecycle

```python
app = d.application("com.example.androidtest")
app.is_installed() / app.is_foreground()
app.start() / app.stop()
app.info() / app.permissions()
app.reset()                 # clear app data
app.clear_cache()
d.current_application()
```

Always verify `app.is_foreground()` before interacting with app UI.

## Selectors

`d(**kwargs)` returns an element handle.

```python
el = d(resourceId="com.example.androidtest:id/btn_login")
el = d(text="登录")
el = d(textContains="欢迎")
el = d(className="android.widget.EditText")
el = d(description="关闭")
```

Useful keys:

`text`, `textContains`, `textStartsWith`, `textMatches`,
`resourceId`, `resourceIdMatches`,
`description`, `descriptionContains`, `descriptionStartsWith`, `descriptionMatches`,
`packageName`, `className`, `clickable`, `enabled`, `checked`, `focused`,
`index`, `instance`.

Preferred order: `resourceId` → `text`/`description` → class/state constraints.
Do not default to coordinates.

## Element actions

```python
el.click()
el.click_exists()
el.long_click()
el.get_text()
el.set_text("text")         # EditText; click/focus first
el.clear_text_field()
el.exists()                 # snapshot only
el.wait_for_exists(5000)    # ms; returns truthy/falsy
el.wait_until_gone(5000)    # ms
el.info()                   # text, bounds, className, ...
el.screenshot(90).save("el.jpg")
el.count()
```

For stale elements after navigation: re-query the selector.

## Scroll and gestures

```python
el.scroll_to(Selector(text="目标项"))
el.fling_from_bottom_to_top()
d().swipe(direction=Direction.DIR_UP, step=32)
d().scroll_from_bottom_to_top_to_end(max_swipes=32, step=60)
d.click(Point(x=540, y=1200))
```

Prefer selector-driven scroll/click over raw points when possible.

## Shell and files

```python
r = d.execute_script("id", timeout=60)
print(r.stdout, r.stderr, r.exitstatus)

d.upload_file("local.apk", "/data/local/tmp/app.apk")
d.download_file("/sdcard/screen.png", "screen.png")
```

There is no `d.shell()`; use `execute_script()`.

## Evidence pattern

```python
from pathlib import Path

case = Path("artifacts/case")
case.mkdir(parents=True, exist_ok=True)
d.screenshot(90).save(case / "step.jpg")
case.joinpath("step.xml").write_bytes(d.dump_window_hierarchy().getvalue())
```

Save evidence for key states and failures. Do not infer UI success from a screenshot alone; pair it with XML/text/app-state assertions.
