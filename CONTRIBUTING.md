# Contributing

1. Create a branch from `main`.
2. Keep credentials and generated files out of commits.
3. Run the checks:

   ```console
   python -m pip install -r requirements.txt
   python -m unittest discover -s tests -v
   node --check browser-extension/background.js
   cd wear-diagnostic
   ./gradlew :app:assembleDebug
   ```

4. Open a pull request describing the provider/device tested and the observed
   playback behavior.
