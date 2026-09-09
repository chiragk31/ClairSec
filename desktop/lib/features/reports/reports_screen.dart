import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';
import '../shared/page_header.dart';
import '../shared/empty_state.dart';

class ReportsScreen extends StatelessWidget {
  const ReportsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: const [
          PageHeader(
            title: 'Reports',
            subtitle: 'Export and review completed scan reports',
          ),
          Expanded(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: EmptyState(
                icon: Icons.description_outlined,
                title: 'No reports generated',
                description:
                    'Complete a scan to generate a report. Reports include '
                    'findings, evidence, source diffs, fix status, and '
                    'verification outcomes.',
              ),
            ),
          ),
        ],
      ),
    );
  }
}
