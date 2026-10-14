import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:excel/excel.dart';
import 'package:scoliosis_flutter/db/state_store.dart';
import 'package:scoliosis_flutter/survey/survey.dart';
import 'package:scoliosis_flutter/roster/student.dart';
import 'package:scoliosis_flutter/roster/records_export.dart';
import 'package:scoliosis_flutter/app/app_controller.dart';
void main() {
 test('final duration survives upload commit and actual SQLite close/reopen',()async {
  final root=Directory('build/duration-reopen-${DateTime.now().microsecondsSinceEpoch}').absolute;
  const student=Student(id:'duration-student',school:'时长回读测试',grade:'一年级',klass:'一班',studentNo:'0001',name:'测试时长');
  final day=DateTime(2026,10,14);final started=DateTime.utc(2026,10,14,5);
  var store=await StateStore.open(root);await store.database.replaceRoster([student]);
  var session=await SurveySession.open(root,student.school,[student],day,store:store);
  await session.prepareCapture('CAM-duration','capture-duration','gate-duration',student);
  expect(await session.startPrepared('CAM-duration','capture-duration','gate-duration'),isTrue);
  expect(await session.recordActualStart('CAM-duration','capture-duration',started),isTrue);
  final receipt=await session.completeCapture(deviceId:'CAM-duration',captureId:'capture-duration',eventId:'duration-event',result:'success',durationMs:10123,gateId:'gate-duration',stopReason:'released',startedAt:started,endedAt:started.add(const Duration(milliseconds:10123)));
  expect(receipt?['durationMs'],10123);
  final temporary=File('${root.path}/fixture-video.bin');await temporary.writeAsBytes([1,2,3]);
  await session.commitFile('CAM-duration','capture-duration',temporary);
  await store.close();session.dispose();
  store=await StateStore.open(root);session=await SurveySession.open(root,student.school,[student],day,store:store);
  expect(session.records.single.captureId,'capture-duration');
  final record=session.records.single;
  final row=RecordRow(captureId:record.captureId,deviceId:record.deviceId,time:record.time,status:'saved',school:student.school,grade:student.grade,klass:student.klass,studentNo:student.studentNo,name:student.name,studentId:student.id,fileName:record.fileName,session:session,record:record);
  expect(finalCaptureDuration(row),10123);
  final book=Excel.decodeBytes(recordsWorkbookBytes([row],{}, {},scope:'时长回读验收',roster:[student]));
  expect(double.parse(book['一年级_一班'].rows[3][5]!.value.toString()),10.123);
  expect(session.completionEvents['duration-event']!['durationMs'],10123);
  await store.close();session.dispose();
 });
}
