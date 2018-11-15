node {
    properties([
            parameters([
                    string(name: 'USER_ID', description: 'the student name'),
                    string(name: 'TASK', description: 'name of the task the student is trying to implement'),
                    string(name: 'REPO_URL', description: 'git repo with the student\'s implementation'),
                    string(name: 'TEST_REPO_URL', description: 'git repo with the tests to the task')
            ])
    ])

    // Directory to where to clone the student's sources
    def sources_dir = "implementation"
    // Directory to where to clone unittests for the task
    def tests_dir = "tests"

    nodejs('NodeJS11') {

        ansiColor('xterm') {

            stage('Preparation') {
                currentBuild.displayName = "#${env.BUILD_NUMBER} ${TASK} ${USER_ID}"
                cleanWs()
            }
            stage('Checkout') {
                // Git clone the student's sources to ${sources_dir} directory
                checkout([$class           : 'GitSCM',
                          branches         : [[name: '*/master']],
                          userRemoteConfigs: [[url: '$REPO_URL']],
                          extensions       : [
                                  [$class: 'CloneOption', noTags: true, reference: '', shallow: true],
                                  [$class: 'RelativeTargetDirectory', relativeTargetDir: "${sources_dir}"]
                          ]
                ])
                // Git clone unittests for the task to ${tests_dir} directory
                checkout([$class           : 'GitSCM',
                          branches         : [[name: '*/master']],
                          userRemoteConfigs: [[url: '$TEST_REPO_URL']],
                          extensions       : [
                                  [$class: 'CloneOption', noTags: true, reference: '', shallow: true],
                                  [$class: 'RelativeTargetDirectory', relativeTargetDir: "${tests_dir}"]
                          ]
                ])
            }
            stage('Test') {
                sh "cp -r ${sources_dir}/src ${tests_dir}"
                dir("${tests_dir}") {
                    sh "npm install"
                    sh "npm test"
                }
            }
            stage('Reporting') {
                sh "ls ${tests_dir}"
                junit testDataPublishers: [[$class: 'AttachmentPublisher']], testResults: "${tests_dir}/report.xml"
            }
        }
    }
}