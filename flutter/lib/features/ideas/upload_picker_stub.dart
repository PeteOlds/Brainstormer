/// Non-web stub for the browser file picker.
class PickedUpload {
  const PickedUpload(this.name, this.bytes);

  final String name;
  final List<int> bytes;
}

/// File picker is only implemented for web; other platforms use file_picker.
Future<PickedUpload?> pickTextFile() async => null;
