import 'dart:async';
import 'dart:convert';
// ignore: avoid_web_libraries_in_flutter, deprecated_member_use
import 'dart:html' as html;
import 'dart:typed_data';

/// Browser-native picker: file_picker cannot always supply bytes on web.
class PickedUpload {
  const PickedUpload(this.name, this.bytes);

  final String name;
  final List<int> bytes;
}

Future<PickedUpload?> pickTextFile() async {
  final input = html.FileUploadInputElement()
    ..accept = '.md,.txt,text/markdown,text/plain';
  html.document.body?.append(input);
  input.click();

  final completer = Completer<PickedUpload?>();
  input.onChange.listen((_) {
    final files = input.files;
    if (files == null || files.isEmpty) {
      input.remove();
      completer.complete(null);
      return;
    }
    final file = files.first;
    final reader = html.FileReader();
    final bytesDone = Completer<List<int>?>();
    reader.onLoadEnd.listen((_) {
      final result = reader.result;
      if (result is ByteBuffer) {
        bytesDone.complete(result.asUint8List().toList());
      } else if (result is String) {
        bytesDone.complete(utf8.encode(result));
      } else {
        bytesDone.complete(null);
      }
    });
    reader.readAsArrayBuffer(file);
    bytesDone.future.then((bytes) {
      input.remove();
      completer.complete(bytes == null ? null : PickedUpload(file.name, bytes));
    });
  });
  return completer.future;
}
