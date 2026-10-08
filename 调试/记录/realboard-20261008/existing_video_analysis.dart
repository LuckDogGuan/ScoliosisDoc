import 'dart:convert';
import 'dart:io';
import 'package:scoliosis_flutter/analysis/angle_analysis.dart';

Future<void> main(List<String> args) async {
  final input = jsonDecode(await File(args[0]).readAsString()) as Map;
  final native = input['native_root'] as String;
  final analyzer = AngleAnalyzer(
    ffmpegPath: '$native/ffmpeg/ffmpeg.exe',
    ffprobePath: '$native/ffmpeg/ffprobe.exe',
    readerPath: '$native/example_read.exe',
    modelVersion: 'thirdPartyLibrary-ruler-video-v1',
  );
  var total = 0;
  final samples = await analyzer.analyze(
    File(input['video'] as String),
    onProgress: (rows, count) async {
      total = count;
      if (rows.length % 10 == 0 || rows.length == count) {
        stdout.writeln('PROGRESS ${rows.length}/$count');
      }
    },
  );
  if (samples.length != total) throw StateError('Incomplete sampling');
  for (var i = 0; i < samples.length; ++i) {
    final sample = samples[i];
    if (sample.frameIndex != 2 + i * 5 ||
        sample.inputImage != 'video-frame/${sample.frameIndex}@${sample.ptsMs}ms' ||
        (sample.angleDeg == null && sample.error == null)) {
      throw StateError('Invalid real-video sample');
    }
  }
  final result = {
    'source_capture_id': input['capture_id'],
    'source_video_sha256': input['video_sha256'],
    'historical_video': true,
    'live_capture_test': false,
    'database_modified': false,
    'model_version': analyzer.modelVersion,
    'sample_count': samples.length,
    'valid_count': samples.where((s) => s.angleDeg != null).length,
    'samples': [
      for (final s in samples)
        {
          'frame_index': s.frameIndex,
          'pts_ms': s.ptsMs,
          'angle_deg': s.angleDeg,
          'error': s.error,
          'input_image': s.inputImage,
        },
    ],
  };
  await File(args[1]).writeAsString(const JsonEncoder.withIndent('  ').convert(result));
  stdout.writeln('DONE samples=${result['sample_count']} valid=${result['valid_count']}');
}
